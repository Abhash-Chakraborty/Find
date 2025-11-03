"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteImage,
  getGallery,
  getImageDetail,
  toggleLike,
  type GalleryResponse,
  type MediaDetail,
  type MediaItem,
} from "@/lib/api";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Heart,
  ImageOff,
  Loader2,
  Trash2,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { formatBytes, formatDate, getStatusBadgeClass } from "@/lib/utils";

function buildEncodedUrlFactory(bucket: string, baseUrl: string) {
  const sanitizedBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;

  return (objectKey?: string | null) => {
    if (!objectKey) {
      return null;
    }

    const encodedKey = objectKey
      .split("/")
      .map((segment) => encodeURIComponent(segment))
      .join("/");

    return `${sanitizedBase}/${bucket}/${encodedKey}`;
  };
}

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

  const bucket = process.env.NEXT_PUBLIC_MINIO_BUCKET ?? "images";
  const minioBaseUrl =
    process.env.NEXT_PUBLIC_MINIO_URL ?? "http://localhost:9000";
  const buildEncodedUrl = useMemo(
    () => buildEncodedUrlFactory(bucket, minioBaseUrl),
    [bucket, minioBaseUrl]
  );

  const galleryQueryKey = useMemo(
    () => ["gallery", page, filter, likedOnly] as const,
    [page, filter, likedOnly]
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

  const detailQuery = useQuery<MediaDetail, Error>({
    queryKey: ["image-detail", selectedMediaId],
    queryFn: () => getImageDetail(selectedMediaId as number),
    enabled: selectedMediaId !== null,
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
        (item) => item.id === selectedMediaId
      );
      if (currentIndex === -1) {
        return;
      }
      const next = data.items[currentIndex + direction];
      if (next) {
        setSelectedMediaId(next.id);
      }
    },
    [data, selectedMediaId]
  );

  const closeDetail = useCallback(() => setSelectedMediaId(null), []);

  useEffect(() => {
    if (selectedMediaId === null) {
      return;
    }

    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDetail();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        goToAdjacent(1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        goToAdjacent(-1);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedMediaId, closeDetail, goToAdjacent]);

  const detailData = detailQuery.data;
  const isDetailLoading = detailQuery.isLoading || detailQuery.isFetching;

  const detailImageSrc = buildEncodedUrl(
    detailData?.minio_key ?? selectedItem?.minio_key ?? null
  );
  const detailLiked = detailData?.liked ?? selectedItem?.liked ?? false;

  const detailDownloadUrl = useMemo(() => {
    if (detailImageSrc) {
      return detailImageSrc;
    }
    if (detailData?.url) {
      return detailData.url;
    }
    if (selectedItem?.url) {
      return selectedItem.url;
    }
    return "";
  }, [detailImageSrc, detailData?.url, selectedItem?.url]);

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
    [likeMutation]
  );

  const handleDeleteRequest = useCallback(
    (mediaId: number, filename?: string) => {
      setDeleteTarget({ id: mediaId, filename });
    },
    []
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
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-7xl px-6 py-12">
        <div className="mb-12">
          <h1 className="mb-3 text-4xl font-light text-black">Gallery</h1>
          <p className="text-sm text-gray-500">Your image collection</p>
        </div>

        <div className="mb-4 flex gap-2 border-b border-gray-100 pb-4">
          {filters.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => {
                setFilter(value);
                setPage(1);
              }}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                filter === value
                  ? "-mb-[17px] border-b-2 border-black text-black"
                  : "text-gray-400 hover:text-gray-600"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="mb-8 flex justify-end">
          <button
            type="button"
            onClick={() => {
              setLikedOnly((previous) => !previous);
              setPage(1);
            }}
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium transition-colors ${
              likedOnly
                ? "bg-black text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            <Heart className={`h-4 w-4 ${likedOnly ? "fill-current" : ""}`} />
            {likedOnly ? "Showing liked images" : "Showing all images"}
          </button>
        </div>

        {isLoading && (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="h-8 w-8 animate-spin text-gray-300" />
          </div>
        )}

        {error && (
          <div className="py-32 text-center">
            <p className="text-gray-400">Failed to load gallery</p>
          </div>
        )}

        {data && data.items.length === 0 && (
          <div className="py-32 text-center">
            <ImageOff className="mx-auto mb-4 h-16 w-16 text-gray-200" />
            <p className="mb-2 text-gray-400">No images found</p>
            <Link href="/upload" className="text-sm text-black hover:underline">
              Upload your first images
            </Link>
          </div>
        )}

        {data && data.items.length > 0 && (
          <>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
              {data.items.map((item) => {
                const imageSrc = buildEncodedUrl(item.minio_key);
                const downloadUrl = imageSrc ?? item.url ?? "";

                return (
                  <div
                    key={item.id}
                    className="group relative aspect-square overflow-hidden rounded-sm border border-gray-100 bg-gray-50 transition-all hover:border-gray-300"
                    onClick={() => setSelectedMediaId(item.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedMediaId(item.id);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    {imageSrc ? (
                      <Image
                        src={imageSrc}
                        alt={item.filename}
                        fill
                        className="object-cover"
                        sizes="(max-width: 768px) 50vw, (max-width: 1200px) 33vw, 16vw"
                        unoptimized
                      />
                    ) : (
                      <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-gray-100 text-gray-400">
                        <ImageOff className="h-8 w-8" />
                        <span className="text-xs">No preview</span>
                      </div>
                    )}

                    <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                      <span className="bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-black">
                        View
                      </span>
                    </div>

                    <div className="absolute inset-0 opacity-0 transition-opacity group-hover:opacity-100">
                      <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent" />
                      <div className="absolute bottom-0 left-0 right-0 space-y-2 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-xs font-medium text-white">
                            {item.filename}
                          </p>
                          <span className={getStatusBadgeClass(item.status)}>
                            {item.status}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              handleToggleLike(item.id);
                            }}
                            disabled={likeMutation.isPending}
                            className={`flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium transition-colors ${
                              item.liked
                                ? "bg-red-500 text-white hover:bg-red-600"
                                : "bg-white/80 text-black hover:bg-white"
                            } ${
                              likeMutation.isPending
                                ? "cursor-not-allowed opacity-70"
                                : ""
                            }`}
                          >
                            <Heart
                              className={`h-3 w-3 ${
                                item.liked ? "fill-current" : ""
                              }`}
                            />
                            {item.liked ? "Unlike" : "Like"}
                          </button>
                          {downloadUrl && (
                            <a
                              href={downloadUrl}
                              download={item.filename}
                              onClick={(event) => event.stopPropagation()}
                              className="flex items-center gap-1 rounded-full bg-white/80 px-2 py-1 text-xs font-medium text-black transition-colors hover:bg-white"
                            >
                              <Download className="h-3 w-3" />
                              Download
                            </a>
                          )}
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              handleDeleteRequest(item.id, item.filename);
                            }}
                            disabled={deleteMutation.isPending}
                            className={`flex items-center gap-1 rounded-full bg-white/80 px-2 py-1 text-xs font-medium text-black transition-colors hover:bg-white ${
                              deleteMutation.isPending
                                ? "cursor-not-allowed opacity-70"
                                : ""
                            }`}
                          >
                            <Trash2 className="h-3 w-3" />
                            Delete
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {data.total > limit && (
              <div className="mt-12 flex items-center justify-center gap-6">
                <button
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page === 1}
                  className="rounded-full p-2 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <span className="text-sm text-gray-500">
                  Page {page} of {Math.ceil(data.total / limit)}
                </span>
                <button
                  onClick={() => setPage((current) => current + 1)}
                  disabled={page >= Math.ceil(data.total / limit)}
                  className="rounded-full p-2 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {selectedItem && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 px-4"
          onClick={closeDetail}
        >
          <div
            className="relative max-h-[90vh] w-full max-w-5xl overflow-hidden rounded-sm bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              onClick={closeDetail}
              className="absolute right-4 top-4 z-20 rounded-full bg-black/70 p-2 text-white transition hover:bg-black"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>

            <div className="grid gap-6 md:grid-cols-[2fr_1fr] md:gap-10">
              <div className="relative h-[55vh] w-full bg-gray-100 md:h-[70vh]">
                {isDetailLoading ? (
                  <div className="flex h-full w-full items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
                  </div>
                ) : detailImageSrc ? (
                  <Image
                    src={detailImageSrc}
                    alt={selectedItem.filename}
                    fill
                    className="object-contain"
                    sizes="(max-width: 1024px) 100vw, 70vw"
                    unoptimized
                  />
                ) : (
                  <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-gray-400">
                    <ImageOff className="h-12 w-12" />
                    <span className="text-sm">Preview unavailable</span>
                  </div>
                )}

                <div className="pointer-events-none absolute inset-y-0 left-0 right-0 flex items-center justify-between px-4">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      goToAdjacent(-1);
                    }}
                    disabled={
                      !data ||
                      selectedMediaId === null ||
                      data.items.findIndex(
                        (item) => item.id === selectedMediaId
                      ) <= 0
                    }
                    className={`pointer-events-auto rounded-full bg-black/60 p-2 text-white transition hover:bg-black ${
                      !data ||
                      selectedMediaId === null ||
                      data.items.findIndex(
                        (item) => item.id === selectedMediaId
                      ) <= 0
                        ? "opacity-40"
                        : "opacity-100"
                    }`}
                    aria-label="Previous"
                  >
                    <ChevronLeft className="h-5 w-5" />
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      goToAdjacent(1);
                    }}
                    disabled={
                      !data ||
                      selectedMediaId === null ||
                      data.items.findIndex(
                        (item) => item.id === selectedMediaId
                      ) >=
                        data.items.length - 1
                    }
                    className={`pointer-events-auto rounded-full bg-black/60 p-2 text-white transition hover:bg-black ${
                      !data ||
                      selectedMediaId === null ||
                      data.items.findIndex(
                        (item) => item.id === selectedMediaId
                      ) >=
                        data.items.length - 1
                        ? "opacity-40"
                        : "opacity-100"
                    }`}
                    aria-label="Next"
                  >
                    <ChevronRight className="h-5 w-5" />
                  </button>
                </div>
              </div>

              <div className="flex max-h-[70vh] flex-col gap-6 overflow-y-auto px-6 pb-6 pt-12 md:pt-10">
                <div>
                  <div className="mb-2 inline-flex items-center gap-2">
                    <span className={getStatusBadgeClass(selectedItem.status)}>
                      {selectedItem.status}
                    </span>
                    <span className="text-xs text-gray-400">
                      ID {selectedItem.id}
                    </span>
                  </div>
                  <h2 className="text-lg font-medium text-black">
                    {selectedItem.filename}
                  </h2>
                  <p className="text-xs text-gray-500">
                    Uploaded{" "}
                    {selectedItem.created_at
                      ? formatDate(selectedItem.created_at)
                      : "Unknown"}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleToggleLike(selectedItem.id)}
                    disabled={likeMutation.isPending}
                    className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      detailLiked
                        ? "bg-red-500 text-white hover:bg-red-600"
                        : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                    } ${
                      likeMutation.isPending
                        ? "cursor-not-allowed opacity-70"
                        : ""
                    }`}
                  >
                    <Heart
                      className={`h-4 w-4 ${detailLiked ? "fill-current" : ""}`}
                    />
                    {detailLiked ? "Unlike" : "Like"}
                  </button>
                  {detailDownloadUrl && (
                    <a
                      href={detailDownloadUrl}
                      download={selectedItem.filename}
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-200"
                    >
                      <Download className="h-4 w-4" />
                      Download
                    </a>
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      handleDeleteRequest(
                        selectedItem.id,
                        selectedItem.filename
                      )
                    }
                    disabled={deleteMutation.isPending}
                    className={`inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-200 ${
                      deleteMutation.isPending
                        ? "cursor-not-allowed opacity-70"
                        : ""
                    }`}
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete
                  </button>
                </div>

                {detailQuery.isError && (
                  <p className="rounded-sm bg-red-50 p-3 text-sm text-red-700">
                    Failed to load additional metadata.
                  </p>
                )}

                <div className="space-y-2 text-sm text-gray-700">
                  {selectedItem.file_size ? (
                    <p>
                      <span className="font-medium text-gray-900">
                        File size:
                      </span>{" "}
                      {formatBytes(selectedItem.file_size)}
                    </p>
                  ) : null}
                  {selectedItem.width && selectedItem.height ? (
                    <p>
                      <span className="font-medium text-gray-900">
                        Dimensions:
                      </span>{" "}
                      {selectedItem.width} × {selectedItem.height}
                    </p>
                  ) : null}
                  <p>
                    <span className="font-medium text-gray-900">Liked:</span>{" "}
                    {detailLiked ? "Yes" : "No"}
                  </p>
                  {detailData?.content_type ? (
                    <p>
                      <span className="font-medium text-gray-900">Type:</span>{" "}
                      {detailData.content_type}
                    </p>
                  ) : null}
                  {detailData?.processed_at ? (
                    <p>
                      <span className="font-medium text-gray-900">
                        Processed:
                      </span>{" "}
                      {formatDate(detailData.processed_at)}
                    </p>
                  ) : null}
                  {detailData?.error ? (
                    <p className="text-red-600">
                      <span className="font-medium">Error:</span>{" "}
                      {detailData.error}
                    </p>
                  ) : null}
                </div>

                {detailData?.metadata?.caption && (
                  <div>
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Caption
                    </h3>
                    <p className="text-sm text-gray-700">
                      {detailData.metadata.caption}
                    </p>
                  </div>
                )}

                {detailData?.metadata?.objects &&
                  detailData.metadata.objects.length > 0 && (
                    <div>
                      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Detected objects
                      </h3>
                      <ul className="space-y-1 text-sm text-gray-700">
                        {detailData.metadata.objects.map((obj, index) => (
                          <li
                            key={`${obj.class}-${index}`}
                            className="flex justify-between"
                          >
                            <span>{obj.class}</span>
                            {typeof obj.confidence === "number" && (
                              <span className="text-gray-500">
                                {Math.round(obj.confidence * 100)}%
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-sm rounded-sm bg-white p-6 shadow-2xl">
            <h2 className="text-lg font-semibold text-black">Delete image?</h2>
            <p className="mt-2 text-sm text-gray-500">
              {deleteTarget.filename
                ? `"${deleteTarget.filename}"`
                : "This image"}{" "}
              will be permanently removed. This action cannot be undone.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={cancelDelete}
                className="rounded-sm border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:border-black hover:text-black"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                disabled={deleteMutation.isPending}
                className="flex items-center gap-2 rounded-sm bg-black px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-900 disabled:cursor-not-allowed disabled:opacity-70"
              >
                <Trash2 className="h-4 w-4" />
                {deleteMutation.isPending ? "Deleting" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deletionError && (
        <div className="fixed bottom-6 right-6 z-[70] flex max-w-sm items-start gap-3 rounded-sm bg-red-600 px-4 py-3 text-white shadow-lg">
          <span className="text-sm font-medium">{deletionError}</span>
          <button
            type="button"
            onClick={() => setDeletionError(null)}
            className="ml-auto text-white/80 transition hover:text-white"
            aria-label="Dismiss error"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
