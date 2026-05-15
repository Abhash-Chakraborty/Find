"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  Heart,
  ImageOff,
  Loader2,
  Trash2,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ImagePreviewModal } from "@/components/image-preview-modal";
import { StatusIndicator } from "@/components/status-indicator";
import {
  deleteImage,
  type GalleryResponse,
  getGallery,
  type MediaItem,
  toggleLike,
} from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";

export default function GalleryPage() {
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<
    "all" | "indexed" | "processing" | "failed"
  >("all");
  const [likedOnly, setLikedOnly] = useState(false);
  const [selectedMediaId, setSelectedMediaId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: number;
    filename?: string;
  } | null>(null);
  const [deletionError, setDeletionError] = useState<string | null>(null);
  const limit = 24;

  const queryClient = useQueryClient();

  const galleryQueryKey = useMemo(
    () => ["gallery", page, filter, likedOnly] as const,
    [page, filter, likedOnly],
  );

  const { data, isLoading, error } = useQuery<GalleryResponse, Error>({
    queryKey: galleryQueryKey,
    queryFn: () =>
      getGallery({
        page,
        limit,
        status: filter === "all" ? undefined : filter,
        liked: likedOnly ? true : undefined,
      }),
    placeholderData: (previous) => previous,
  });

  const likeMutation = useMutation({
    mutationFn: (mediaId: number) => toggleLike(mediaId),
    onSuccess: ({ id }) => {
      queryClient.invalidateQueries({ queryKey: ["gallery"] });
      queryClient.invalidateQueries({ queryKey: ["image-detail", id] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (mediaId: number) => deleteImage(mediaId),
    onMutate: async (mediaId: number) => {
      setDeletionError(null);

      await queryClient.cancelQueries({ queryKey: galleryQueryKey });

      const previousData =
        queryClient.getQueryData<GalleryResponse>(galleryQueryKey);

      queryClient.setQueryData<GalleryResponse>(galleryQueryKey, (old) => {
        if (!old) {
          return old;
        }
        const filteredItems = old.items.filter((item) => item.id !== mediaId);
        if (filteredItems.length === old.items.length) {
          return old;
        }
        return {
          ...old,
          items: filteredItems,
          total: Math.max(0, old.total - 1),
        };
      });

      setSelectedMediaId((current) => (current === mediaId ? null : current));
      return { previousData };
    },
    onError: (mutationError, _variables, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(galleryQueryKey, context.previousData);
      }

      const message =
        mutationError instanceof Error
          ? mutationError.message
          : "Failed to delete image. Please try again.";
      setDeletionError(message);
    },
    onSuccess: ({ id }) => {
      queryClient.invalidateQueries({ queryKey: ["image-detail", id] });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["gallery"] });
    },
  });

  const selectedItem = useMemo<MediaItem | null>(() => {
    if (!data || selectedMediaId === null) {
      return null;
    }
    return data.items.find((item) => item.id === selectedMediaId) ?? null;
  }, [data, selectedMediaId]);

  const selectedIndex = useMemo(() => {
    if (!data || selectedMediaId === null) {
      return -1;
    }
    return data.items.findIndex((item) => item.id === selectedMediaId);
  }, [data, selectedMediaId]);

  useEffect(() => {
    if (!data || selectedMediaId === null) {
      return;
    }
    if (!data.items.some((item) => item.id === selectedMediaId)) {
      setSelectedMediaId(null);
    }
  }, [data, selectedMediaId]);

  const goToAdjacent = useCallback(
    (direction: -1 | 1) => {
      if (!data || selectedMediaId === null) {
        return;
      }
      const currentIndex = data.items.findIndex(
        (item) => item.id === selectedMediaId,
      );
      if (currentIndex === -1) {
        return;
      }
      const next = data.items[currentIndex + direction];
      if (next) {
        setSelectedMediaId(next.id);
      }
    },
    [data, selectedMediaId],
  );

  const closeDetail = useCallback(() => setSelectedMediaId(null), []);

  const filters = [
    { label: "All", value: "all" as const },
    { label: "Indexed", value: "indexed" as const },
    { label: "Processing", value: "processing" as const },
    { label: "Failed", value: "failed" as const },
  ];

  const handleToggleLike = useCallback(
    (mediaId: number) => {
      likeMutation.mutate(mediaId);
    },
    [likeMutation],
  );

  const handleDeleteRequest = useCallback(
    (mediaId: number, filename?: string) => {
      setDeleteTarget({ id: mediaId, filename });
    },
    [],
  );

  const confirmDelete = useCallback(() => {
    if (!deleteTarget) {
      return;
    }
    deleteMutation.mutate(deleteTarget.id);
    setDeleteTarget(null);
  }, [deleteMutation, deleteTarget]);

  const cancelDelete = useCallback(() => {
    setDeleteTarget(null);
  }, []);

  return (
    <div className="page-shell">
      <div className="container-shell py-10 md:py-14">
        <div className="page-enter mx-auto mb-10 max-w-2xl text-center">
          <h1 className="section-heading mb-4 text-5xl font-medium md:text-6xl">
            Gallery
          </h1>
          <p className="muted-copy text-sm leading-6">
            Your entire visual collection, automatically analyzed and indexed.
          </p>
        </div>

        <div className="frost-panel delayed-enter mb-8 flex flex-col items-center justify-between gap-4 rounded-3xl px-4 py-3 md:flex-row">
          <div className="flex flex-wrap justify-center gap-1">
            {filters.map(({ label, value }) => (
              <button
                type="button"
                key={value}
                onClick={() => {
                  setFilter(value);
                  setPage(1);
                }}
                className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                  filter === value
                    ? "bg-white text-black"
                    : "text-[#a1a4a5] hover:bg-white/[0.08] hover:text-[#f0f0f0]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => {
              setLikedOnly((previous) => !previous);
              setPage(1);
            }}
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium transition-colors ${
              likedOnly
                ? "border border-[var(--red-soft)] bg-[var(--red-soft)] text-[#ff9bab]"
                : "border border-[var(--frost)] text-[#a1a4a5] hover:bg-white/[0.08] hover:text-[#f0f0f0]"
            }`}
          >
            <Heart className={`h-4 w-4 ${likedOnly ? "fill-current" : ""}`} />
            {likedOnly ? "Liked" : "All images"}
          </button>
        </div>

        {isLoading && (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="h-8 w-8 animate-spin text-[#a1a4a5]" />
          </div>
        )}

        {error && (
          <div className="py-32 text-center">
            <p className="text-[#a1a4a5]">Failed to load gallery</p>
          </div>
        )}

        {data && data.items.length === 0 && (
          <div className="w-full">
            <div className="frost-panel mx-auto rounded-3xl px-8 py-16 text-center">
              <ImageOff className="mx-auto mb-4 h-12 w-12 text-[#5f6568]" />
              <p className="mb-2 text-[#f0f0f0]">No images found</p>
              <Link
                href="/upload"
                className="text-sm text-[#3b9eff] hover:underline"
              >
                Upload your first images
              </Link>
            </div>
          </div>
        )}

        {data && data.items.length > 0 && (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">
              {data.items.map((item) => {
                const imageSrc = resolveMediaUrl(item.url, item.minio_key);
                const downloadUrl = imageSrc ?? item.url ?? "";

                return (
                  <article
                    key={item.id}
                    className="frost-panel card-hover group relative overflow-hidden rounded-2xl"
                  >
                    <button
                      type="button"
                      className="relative block aspect-square w-full overflow-hidden bg-white/[0.025] text-left focus:outline-none"
                      onClick={() => setSelectedMediaId(item.id)}
                      aria-label={`View ${item.filename}`}
                    >
                      {imageSrc ? (
                        <Image
                          src={imageSrc}
                          alt={item.filename}
                          fill
                          className="object-cover transition duration-500 group-hover:scale-[1.035]"
                          sizes="(max-width: 768px) 50vw, (max-width: 1200px) 25vw, 16vw"
                          unoptimized
                        />
                      ) : (
                        <div
                          className="flex h-full w-full flex-col items-center justify-center gap-2 text-[#5f6568]"
                          role="img"
                          aria-label="No preview available"
                        >
                          <ImageOff className="h-7 w-7" />
                          <span className="text-xs">No preview</span>
                        </div>
                      )}

                      <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/12 to-transparent opacity-60 transition-opacity group-hover:opacity-90" />
                      <StatusIndicator
                        status={item.status}
                        className="absolute bottom-3 right-3"
                      />
                      <div className="absolute inset-0 grid place-items-center opacity-0 transition duration-200 group-hover:opacity-100">
                        <span className="icon-button h-10 w-10 bg-black/[0.45] backdrop-blur-md">
                          <Eye className="h-4 w-4" />
                        </span>
                      </div>
                    </button>

                    <div className="space-y-3 p-3">
                      <p className="truncate text-xs font-medium text-[#f0f0f0]">
                        {item.filename}
                      </p>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleToggleLike(item.id)}
                          disabled={likeMutation.isPending}
                          className={`icon-button h-8 w-8 ${
                            item.liked ? "text-[#ff9bab]" : "text-[#a1a4a5]"
                          } ${
                            likeMutation.isPending
                              ? "cursor-not-allowed opacity-70"
                              : ""
                          }`}
                          aria-label={
                            item.liked ? "Unlike image" : "Like image"
                          }
                        >
                          <Heart
                            className={`h-3.5 w-3.5 ${
                              item.liked ? "fill-current" : ""
                            }`}
                          />
                        </button>
                        {downloadUrl && (
                          <a
                            href={downloadUrl}
                            download={item.filename}
                            className="icon-button h-8 w-8 text-[#a1a4a5]"
                            aria-label="Download image"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </a>
                        )}
                        <button
                          type="button"
                          onClick={() =>
                            handleDeleteRequest(item.id, item.filename)
                          }
                          disabled={deleteMutation.isPending}
                          className={`icon-button h-8 w-8 text-[#a1a4a5] ${
                            deleteMutation.isPending
                              ? "cursor-not-allowed opacity-70"
                              : ""
                          }`}
                          aria-label="Delete image"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>

            {data.total > limit && (
              <div className="mt-12 flex items-center justify-center gap-6">
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page === 1}
                  className="icon-button disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <span className="text-sm text-[#a1a4a5]">
                  Page {page} of {Math.ceil(data.total / limit)}
                </span>
                <button
                  type="button"
                  onClick={() => setPage((current) => current + 1)}
                  disabled={page >= Math.ceil(data.total / limit)}
                  className="icon-button disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {selectedItem && (
        <ImagePreviewModal
          media={selectedItem}
          onClose={closeDetail}
          onPrevious={() => goToAdjacent(-1)}
          onNext={() => goToAdjacent(1)}
          hasPrevious={selectedIndex > 0}
          hasNext={
            data
              ? selectedIndex >= 0 && selectedIndex < data.items.length - 1
              : false
          }
          onDeleted={(mediaId) => {
            if (selectedMediaId === mediaId) {
              setSelectedMediaId(null);
            }
          }}
        />
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 px-4 backdrop-blur-lg">
          <div className="frost-panel page-enter w-full max-w-sm rounded-3xl p-6">
            <h2 className="text-lg font-semibold text-[#f0f0f0]">
              Delete image?
            </h2>
            <p className="mt-2 text-sm text-[#a1a4a5]">
              {deleteTarget.filename
                ? `"${deleteTarget.filename}"`
                : "This image"}{" "}
              will be permanently removed. This action cannot be undone.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={cancelDelete}
                className="frost-button px-4 py-2 text-sm font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                disabled={deleteMutation.isPending}
                className="inline-flex items-center gap-2 rounded-full border border-[var(--red-soft)] bg-[var(--red-soft)] px-4 py-2 text-sm font-medium text-[#ff9bab] transition hover:bg-[#ff2047]/25 disabled:cursor-not-allowed disabled:opacity-70"
              >
                <Trash2 className="h-4 w-4" />
                {deleteMutation.isPending ? "Deleting" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deletionError && (
        <div className="fixed bottom-6 right-6 z-[70] flex max-w-sm items-start gap-3 rounded-2xl border border-[var(--red-soft)] bg-black/90 px-4 py-3 text-[#ff9bab] shadow-lg backdrop-blur-lg">
          <span className="text-sm font-medium">{deletionError}</span>
          <button
            type="button"
            onClick={() => setDeletionError(null)}
            className="ml-auto text-[#ff9bab]/80 transition hover:text-[#ff9bab]"
            aria-label="Dismiss error"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
