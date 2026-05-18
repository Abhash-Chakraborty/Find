"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Heart,
  ImageOff,
  Loader2,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  deleteImage,
  getImageDetail,
  type MediaDetail,
  type MediaItem,
  reprocessImage,
  toggleLike,
} from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";
import { formatBytes, formatDate } from "@/lib/utils";
import { StatusIndicator } from "./status-indicator";

export type PreviewMedia = Pick<MediaItem, "id" | "filename"> &
  Partial<
    Pick<
      MediaItem,
      | "url"
      | "minio_key"
      | "status"
      | "created_at"
      | "processed_at"
      | "width"
      | "height"
      | "file_size"
      | "cluster_id"
      | "liked"
      | "caption"
      | "objects"
    >
  >;

type ImagePreviewModalProps = {
  media: PreviewMedia;
  onClose: () => void;
  onDeleted?: (mediaId: number) => void;
  onLikedChange?: (mediaId: number, liked: boolean) => void;
  onPrevious?: () => void;
  onNext?: () => void;
  hasPrevious?: boolean;
  hasNext?: boolean;
};

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[var(--frost-soft)] py-2.5 last:border-b-0">
      <dt className="text-xs font-medium uppercase text-[color:var(--muted)]">
        {label}
      </dt>
      <dd className="max-w-[62%] text-right text-sm text-[color:var(--near-white)]">
        {children}
      </dd>
    </div>
  );
}

export function ImagePreviewModal({
  media,
  onClose,
  onDeleted,
  onLikedChange,
  onPrevious,
  onNext,
  hasPrevious = false,
  hasNext = false,
}: ImagePreviewModalProps) {
  const queryClient = useQueryClient();
  const [likedOverride, setLikedOverride] = useState<boolean | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const detailQuery = useQuery<MediaDetail, Error>({
    queryKey: ["image-detail", media.id],
    queryFn: () => getImageDetail(media.id),
    enabled: media.id !== null,
  });

  useEffect(() => {
    if (media.id) {
      setLikedOverride(null);
      setConfirmingDelete(false);
    }
  }, [media.id]);

  const detailData = detailQuery.data;
  const isDetailLoading = detailQuery.isLoading || detailQuery.isFetching;

  const imageSrc = resolveMediaUrl(
    detailData?.url ?? media.url,
    detailData?.minio_key ?? media.minio_key,
  );
  const downloadUrl = useMemo(() => {
    if (detailData?.url) {
      return detailData.url;
    }
    if (media.url) {
      return media.url;
    }
    return imageSrc ?? "";
  }, [detailData?.url, imageSrc, media.url]);

  const detailLiked =
    likedOverride ?? detailData?.liked ?? media.liked ?? false;
  const status = detailData?.status ?? media.status ?? "pending";
  const clusterId = detailData?.cluster_id ?? media.cluster_id;
  const uploadedAt = detailData?.created_at ?? media.created_at;
  const processedAt = detailData?.processed_at ?? media.processed_at;
  const caption =
    detailData?.metadata?.caption ?? detailData?.caption ?? media.caption;
  const objects = detailData?.metadata?.objects ?? detailData?.objects ?? [];
  const ocrText = detailData?.metadata?.ocr_text;

  const likeMutation = useMutation({
    mutationFn: (mediaId: number) => toggleLike(mediaId),
    onSuccess: ({ id, liked }) => {
      setLikedOverride(liked);
      onLikedChange?.(id, liked);
      queryClient.invalidateQueries({ queryKey: ["gallery"] });
      queryClient.invalidateQueries({ queryKey: ["image-detail", id] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (mediaId: number) => deleteImage(mediaId),
    onSuccess: ({ id }) => {
      queryClient.invalidateQueries({ queryKey: ["gallery"] });
      queryClient.invalidateQueries({ queryKey: ["clusters"] });
      queryClient.invalidateQueries({ queryKey: ["image-detail", id] });
      onDeleted?.(id);
      onClose();
    },
  });

  const reprocessMutation = useMutation({
    mutationFn: (mediaId: number) => reprocessImage(mediaId),
    onSuccess: ({ media_id }) => {
      queryClient.invalidateQueries({ queryKey: ["gallery"] });
      queryClient.invalidateQueries({ queryKey: ["image-detail", media_id] });
      toast.success("Retry queued — analysis will restart shortly.");
    },
    onError: () => {
      toast.error(
        "Retry failed. The queue may be unavailable — please try again.",
      );
    },
  });

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (event.key === "ArrowLeft" && hasPrevious && onPrevious) {
        event.preventDefault();
        onPrevious();
      }
      if (event.key === "ArrowRight" && hasNext && onNext) {
        event.preventDefault();
        onNext();
      }
    },
    [hasNext, hasPrevious, onClose, onNext, onPrevious],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      className="fixed inset-0 z-50 flex h-dvh w-full items-center justify-center bg-black/75 p-2 backdrop-blur-2xl md:p-4"
      role="presentation"
    >
      <button
        type="button"
        className="absolute inset-0 h-full w-full cursor-default"
        onClick={onClose}
        aria-label="Close detail view"
      />
      <div
        className="frost-panel page-enter relative grid h-[calc(100dvh-1rem)] w-full max-w-7xl grid-rows-[minmax(0,1fr)_minmax(320px,42dvh)] overflow-hidden rounded-3xl bg-[color:var(--void)] md:h-[calc(100dvh-2rem)] md:grid-cols-[minmax(0,1fr)_minmax(380px,430px)] md:grid-rows-1"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Image details"
      >
        <div className="relative min-h-0 bg-[color:var(--image-stage)]">
          {isDetailLoading ? (
            <div className="flex h-full w-full items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-[color:var(--silver)]" />
            </div>
          ) : imageSrc ? (
            <Image
              src={imageSrc}
              alt={media.filename}
              fill
              className="object-contain p-3 md:p-6"
              sizes="(max-width: 1024px) 100vw, 72vw"
              unoptimized
            />
          ) : (
            <div
              className="flex h-full w-full flex-col items-center justify-center gap-3 text-[color:var(--muted)]"
              role="img"
              aria-label="Preview unavailable"
            >
              <ImageOff className="h-12 w-12" />
              <span className="text-sm">Preview unavailable</span>
            </div>
          )}

          {(onPrevious || onNext) && (
            <div className="pointer-events-none absolute inset-y-0 left-0 right-0 flex items-center justify-between px-4">
              <button
                type="button"
                onClick={onPrevious}
                disabled={!hasPrevious}
                className={`icon-button pointer-events-auto bg-[color:var(--overlay)] text-white backdrop-blur-md ${
                  hasPrevious ? "opacity-100" : "opacity-35"
                }`}
                aria-label="Previous"
              >
                <ChevronLeft className="h-5 w-5" />
              </button>
              <button
                type="button"
                onClick={onNext}
                disabled={!hasNext}
                className={`icon-button pointer-events-auto bg-[color:var(--overlay)] text-white backdrop-blur-md ${
                  hasNext ? "opacity-100" : "opacity-35"
                }`}
                aria-label="Next"
              >
                <ChevronRight className="h-5 w-5" />
              </button>
            </div>
          )}

          <div className="pointer-events-none absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-5">
            <p className="max-w-[calc(100%-3rem)] truncate text-sm font-medium text-white">
              {media.filename}
            </p>
          </div>
        </div>

        <aside className="flex min-h-0 flex-col border-t border-[var(--frost)] bg-[color:var(--overlay-strong)] md:border-l md:border-t-0">
          <div className="flex items-start justify-between gap-4 border-b border-[var(--frost)] px-5 py-5 md:px-6">
            <div className="min-w-0">
              <div className="mb-3 flex items-center gap-2">
                <StatusIndicator status={status} />
                <span className="text-xs text-[color:var(--muted)]">
                  ID {media.id}
                </span>
              </div>
              <h2 className="break-words text-xl font-medium leading-tight text-[color:var(--near-white)]">
                {media.filename}
              </h2>
              <p className="mt-2 text-xs text-[color:var(--silver)]">
                Uploaded {uploadedAt ? formatDate(uploadedAt) : "Unknown"}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="icon-button h-9 w-9 shrink-0 bg-[color:var(--surface-soft)]"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 md:px-6">
            {detailQuery.isError && (
              <p className="mb-4 rounded-2xl border border-[var(--red-soft)] bg-[var(--red-soft)] p-3 text-sm text-[#ff9bab]">
                Failed to load additional metadata.
              </p>
            )}

            <section className="mb-6">
              <h3 className="mb-2 text-xs font-semibold uppercase text-[color:var(--muted)]">
                File
              </h3>
              <dl className="rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-4">
                {(detailData?.file_size ?? media.file_size) ? (
                  <DetailRow label="Size">
                    {formatBytes(detailData?.file_size ?? media.file_size ?? 0)}
                  </DetailRow>
                ) : null}
                {(detailData?.width ?? media.width) &&
                (detailData?.height ?? media.height) ? (
                  <DetailRow label="Dimensions">
                    {detailData?.width ?? media.width} ×{" "}
                    {detailData?.height ?? media.height}
                  </DetailRow>
                ) : null}
                {typeof clusterId === "number" && (
                  <DetailRow label="Cluster">
                    <Link
                      href="/clusters"
                      className="text-[color:var(--blue)] underline"
                    >
                      Cluster {clusterId}
                    </Link>
                  </DetailRow>
                )}
                {detailData?.content_type ? (
                  <DetailRow label="Type">{detailData.content_type}</DetailRow>
                ) : null}
                {processedAt ? (
                  <DetailRow label="Processed">
                    {formatDate(processedAt)}
                  </DetailRow>
                ) : null}
              </dl>
            </section>

            <section className="mb-6">
              <h3 className="mb-2 text-xs font-semibold uppercase text-[color:var(--muted)]">
                Caption
              </h3>
              <div className="rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-4">
                <p className="text-sm leading-6 text-[color:var(--near-white)]">
                  {caption || "No caption generated yet."}
                </p>
              </div>
            </section>

            <section className="mb-6">
              <h3 className="mb-2 text-xs font-semibold uppercase text-[color:var(--muted)]">
                Metadata
              </h3>
              <div className="space-y-3 rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-4">
                {objects.length > 0 ? (
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase text-[color:var(--muted)]">
                      Detected objects
                    </p>
                    <ul className="space-y-1.5 text-sm text-[color:var(--near-white)]">
                      {objects.map((obj) => (
                        <li
                          key={`${obj.class}-${obj.confidence}-${obj.bbox.x1}-${obj.bbox.y1}-${obj.bbox.x2}-${obj.bbox.y2}`}
                          className="flex justify-between gap-4"
                        >
                          <span>{obj.class}</span>
                          {typeof obj.confidence === "number" && (
                            <span className="text-[color:var(--muted)]">
                              {Math.round(obj.confidence * 100)}%
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="text-sm text-[color:var(--silver)]">
                    No detected objects yet.
                  </p>
                )}

                {ocrText && (
                  <div className="border-t border-[var(--frost-soft)] pt-3">
                    <p className="mb-2 text-xs font-medium uppercase text-[color:var(--muted)]">
                      OCR text
                    </p>
                    <p className="max-h-36 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--near-white)]">
                      {ocrText}
                    </p>
                  </div>
                )}
              </div>
            </section>

            {detailData?.error && (
              <p className="rounded-2xl border border-[var(--red-soft)] bg-[var(--red-soft)] p-3 text-sm text-[#ff9bab]">
                {detailData.error}
              </p>
            )}
          </div>

          <div className="border-t border-[var(--frost)] px-5 py-4 md:px-6">
            {confirmingDelete ? (
              <div className="space-y-3">
                <p className="text-sm text-[#ff9bab]">
                  Delete this image permanently?
                </p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setConfirmingDelete(false)}
                    className="frost-button px-4 py-2 text-sm font-medium"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteMutation.mutate(media.id)}
                    disabled={deleteMutation.isPending}
                    className="inline-flex items-center gap-2 rounded-full border border-[var(--red-soft)] bg-[var(--red-soft)] px-4 py-2 text-sm font-medium text-[#ff9bab] transition hover:bg-[#ff2047]/25 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    <Trash2 className="h-4 w-4" />
                    {deleteMutation.isPending ? "Deleting" : "Delete"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                {(status === "failed" ||
                  (status === "indexed" && !caption)) && (
                  <button
                    type="button"
                    onClick={() => reprocessMutation.mutate(media.id)}
                    disabled={reprocessMutation.isPending}
                    className="frost-button inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-[color:var(--silver)] disabled:cursor-not-allowed disabled:opacity-70"
                    aria-label="Retry analysis"
                  >
                    <RotateCcw
                      className={`h-4 w-4 ${reprocessMutation.isPending ? "animate-spin" : ""}`}
                    />
                    {reprocessMutation.isPending
                      ? "Retrying…"
                      : "Retry Analysis"}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => likeMutation.mutate(media.id)}
                  disabled={likeMutation.isPending}
                  className={`frost-button px-4 py-2 text-sm font-medium ${
                    detailLiked
                      ? "border-[var(--red)] bg-[var(--red-soft)] text-[color:var(--red)]"
                      : "text-[color:var(--silver)]"
                  } ${
                    likeMutation.isPending
                      ? "cursor-not-allowed opacity-70"
                      : ""
                  }`}
                  aria-label={detailLiked ? "Unlike image" : "Like image"}
                >
                  <Heart
                    className={`h-4 w-4 ${detailLiked ? "fill-current" : ""}`}
                  />
                  {detailLiked ? "Liked" : "Like"}
                </button>
                {downloadUrl && (
                  <a
                    href={downloadUrl}
                    download={media.filename}
                    rel="noopener noreferrer"
                    className="frost-button px-4 py-2 text-sm font-medium text-[color:var(--silver)]"
                  >
                    <Download className="h-4 w-4" />
                    Download
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(true)}
                  className="frost-button px-4 py-2 text-sm font-medium text-[color:var(--silver)]"
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </button>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
