"use client";

import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import axios from "axios";
import {
  Download,
  Eye,
  Heart,
  ImageOff,
  Lock,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  ImagePreviewModal,
  type PreviewMedia,
} from "@/components/image-preview-modal";
import { StatusIndicator } from "@/components/status-indicator";
import {
  api,
  deleteImage,
  type GalleryResponse,
  getGallery,
  getImageDetail,
  reprocessImage,
  toggleLike,
} from "@/lib/api";
import {
  MINIO_URL_REFRESH_INTERVAL_MS,
  MINIO_URL_STALE_TIME_MS,
  resolveMediaUrl,
} from "@/lib/media";
import { vaultStore } from "@/store/vaultStore";

const GALLERY_LIMIT = 24;
const GALLERY_SKELETON_COUNT = GALLERY_LIMIT;

type GalleryFilter = "all" | "indexed" | "processing" | "failed";

type GalleryEmptyState = {
  title: string;
  subtitle: string | null;
  showUploadLink: boolean;
  showClearLikedOnly: boolean;
};

/**
 * Determines the appropriate empty state messaging based on current gallery filters.
 * @param filter - The current status filter applied to the gallery.
 * @param likedOnly - Whether the gallery is currently filtered to show only liked images.
 * @returns A configuration object for the empty state UI.
 */
function getGalleryEmptyState(
  filter: GalleryFilter,
  likedOnly: boolean,
): GalleryEmptyState {
  if (filter === "all") {
    if (likedOnly) {
      return {
        title: "No liked images yet",
        subtitle: "Like an image to save it here.",
        showUploadLink: false,
        showClearLikedOnly: true,
      };
    }

    return {
      title: "No images found",
      subtitle: null,
      showUploadLink: true,
      showClearLikedOnly: false,
    };
  }

  if (filter === "indexed") {
    return likedOnly
      ? {
          title: "No liked indexed images yet",
          subtitle:
            "Try uploading images or check the Processing tab for items still in progress.",
          showUploadLink: false,
          showClearLikedOnly: true,
        }
      : {
          title: "No indexed images yet",
          subtitle:
            "Try uploading images or check the Processing tab for items still in progress.",
          showUploadLink: false,
          showClearLikedOnly: false,
        };
  }

  if (filter === "processing") {
    return likedOnly
      ? {
          title: "No liked images are processing",
          subtitle:
            "None of your liked images are queued or running right now.",
          showUploadLink: false,
          showClearLikedOnly: true,
        }
      : {
          title: "All clear",
          subtitle: "No images are processing right now.",
          showUploadLink: false,
          showClearLikedOnly: false,
        };
  }

  return likedOnly
    ? {
        title: "No failed liked images",
        subtitle: "None of your liked images have failed recently.",
        showUploadLink: false,
        showClearLikedOnly: true,
      }
    : {
        title: "No failed images",
        subtitle: "Nothing failed recently.",
        showUploadLink: false,
        showClearLikedOnly: false,
      };
}

/**
 * Maps a raw URL status parameter to a strongly-typed GalleryFilter.
 * @param status - The raw string parameter from the URL.
 * @returns The resolved GalleryFilter type.
 */
const getFilterFromStatusParam = (status: string | null): GalleryFilter => {
  if (status === "completed" || status === "indexed") {
    return "indexed";
  }

  if (status === "processing" || status === "failed") {
    return status;
  }

  return "all";
};

/**
 * Maps a strongly-typed GalleryFilter back to a URL-friendly status string.
 * @param filter - The active GalleryFilter type.
 * @returns The string value to use in the URL, or null if no filter should be applied.
 */
const getStatusParamFromFilter = (filter: GalleryFilter): string | null => {
  if (filter === "all") {
    return null;
  }

  return filter === "indexed" ? "completed" : filter;
};

type GalleryThumbnailProps = {
  src: string;
  alt: string;
};

type GallerySkeletonGridProps = {
  count: number;
  label?: string;
};

/**
 * Keeps the thumbnail area stable when no preview URL exists or an image fails to load.
 */
function GalleryImageFallback() {
  return (
    <div
      className="flex h-full w-full flex-col items-center justify-center gap-2 bg-[color:var(--surface-soft)] text-[color:var(--muted)]"
      role="img"
      aria-label="No preview available"
    >
      <ImageOff className="h-7 w-7" />
      <span className="text-xs">No preview</span>
    </div>
  );
}

/**
 * Shows a lightweight, theme-aware skeleton while each thumbnail image loads.
 */
function GalleryThumbnail({ src, alt }: GalleryThumbnailProps) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    setIsLoaded(false);
    setHasError(false);
  }, [src]);

  if (hasError) {
    return <GalleryImageFallback />;
  }

  return (
    <>
      {!isLoaded && (
        <div
          className="absolute inset-0 animate-pulse bg-[color:var(--surface-soft)]"
          aria-hidden="true"
        />
      )}
      <Image
        src={src}
        alt={alt}
        fill
        className={`object-cover transition duration-500 group-hover:scale-[1.035] ${
          isLoaded ? "opacity-100" : "opacity-0"
        }`}
        sizes="(max-width: 768px) 50vw, (max-width: 1200px) 25vw, 16vw"
        unoptimized
        onLoad={() => setIsLoaded(true)}
        onError={() => {
          setIsLoaded(true);
          setHasError(true);
        }}
      />
    </>
  );
}

/**
 * Matches the real gallery card dimensions so content does not jump when data arrives.
 */
function GalleryCardSkeleton() {
  return (
    <article
      className="frost-panel overflow-hidden rounded-2xl"
      aria-hidden="true"
    >
      <div className="relative aspect-square w-full overflow-hidden bg-[color:var(--surface-soft)]">
        <div className="absolute inset-0 animate-pulse bg-[color:var(--surface-soft)]" />
        <div className="absolute inset-x-6 top-1/2 h-2 -translate-y-1/2 rounded-full bg-[color:var(--frost-soft)]" />
        <div className="absolute bottom-3 right-3 h-5 w-16 rounded-full bg-[color:var(--frost-soft)]" />
      </div>

      <div className="space-y-3 p-3">
        <div className="h-3 w-3/4 animate-pulse rounded-full bg-[color:var(--frost-soft)]" />
        <div className="flex items-center gap-2">
          {Array.from({ length: 4 }, (_, index) => (
            <div
              key={index}
              className="h-8 w-8 animate-pulse rounded-full bg-[color:var(--frost-soft)]"
            />
          ))}
        </div>
      </div>
    </article>
  );
}

/**
 * Renders lightweight loading placeholders for the gallery grid.
 */
function GallerySkeletonGrid({
  count,
  label = "Loading gallery images…",
}: GallerySkeletonGridProps) {
  return (
    <div
      className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6"
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <span className="sr-only">{label}</span>
      {Array.from({ length: count }, (_, index) => (
        <GalleryCardSkeleton key={`gallery-skeleton-${index}`} />
      ))}
    </div>
  );
}

/**
 * Core gallery component managing infinite scrolling, filtering, and media interactions.
 * Uses React Query's useInfiniteQuery for paginated data fetching and client-side caching.
 */
function GalleryPageContent() {
  const [selectedMediaId, setSelectedMediaId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: number;
    filename?: string;
  } | null>(null);
  const [deletionError, setDeletionError] = useState<string | null>(null);
  const [hasOpenedFromQuery, setHasOpenedFromQuery] = useState(false);
  const [querySelectedItem, setQuerySelectedItem] =
    useState<PreviewMedia | null>(null);

  const queryClient = useQueryClient();
  const isVaultUnlocked = vaultStore((state) => state.isUnlocked);
  const vaultSessionToken = vaultStore((state) => state.sessionToken);
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const filter = getFilterFromStatusParam(searchParams.get("status"));
  const likedOnly = searchParams.get("liked") === "true";

  // The query key includes filter + likedOnly so any URL filter change
  // automatically resets the infinite query back to page 1.
  const galleryQueryKey = ["gallery-infinite", filter, likedOnly] as const;

  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery<GalleryResponse, Error>({
    queryKey: galleryQueryKey,
    queryFn: ({ pageParam }) =>
      getGallery({
        page: typeof pageParam === "number" ? pageParam : 1,
        limit: GALLERY_LIMIT,
        status: filter === "all" ? undefined : filter,
        liked: likedOnly ? true : undefined,
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      const fetchedSoFar = lastPage.page * lastPage.limit;
      return fetchedSoFar < lastPage.total ? lastPage.page + 1 : undefined;
    },
    staleTime: MINIO_URL_STALE_TIME_MS,
    refetchInterval: (query) => {
      const pages = query.state.data?.pages;
      const hasProcessing = pages?.some((page) =>
        page.items.some(
          (item) => item.status === "processing" || item.status === "pending",
        ),
      );
      return hasProcessing ? 5000 : MINIO_URL_REFRESH_INTERVAL_MS;
    },
  });

  // Flat list of all items across all loaded pages.
  const allItems = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data],
  );

  const total = data?.pages[0]?.total ?? 0;
  const isInitialGalleryLoading = isLoading && allItems.length === 0;
  const loadingMoreSkeletonCount = useMemo(() => {
    if (!isFetchingNextPage || allItems.length === 0) {
      return 0;
    }

    if (total > allItems.length) {
      return Math.min(GALLERY_SKELETON_COUNT, total - allItems.length);
    }

    return GALLERY_SKELETON_COUNT;
  }, [isFetchingNextPage, allItems.length, total]);

  const buildGalleryHref = useCallback(
    (nextState: { filter?: GalleryFilter; likedOnly?: boolean }) => {
      const nextFilter = nextState.filter ?? filter;
      const nextLikedOnly = nextState.likedOnly ?? likedOnly;
      const nextParams = new URLSearchParams(searchParams.toString());
      const statusParam = getStatusParamFromFilter(nextFilter);

      if (statusParam) {
        nextParams.set("status", statusParam);
      } else {
        nextParams.delete("status");
      }

      if (nextLikedOnly) {
        nextParams.set("liked", "true");
      } else {
        nextParams.delete("liked");
      }

      const queryString = nextParams.toString();
      return queryString ? `${pathname}?${queryString}` : pathname;
    },
    [filter, likedOnly, pathname, searchParams],
  );

  const updateGalleryParams = useCallback(
    (nextState: { filter?: GalleryFilter; likedOnly?: boolean }) => {
      router.push(buildGalleryHref(nextState), {
        scroll: false,
      });
    },
    [buildGalleryHref, router],
  );

  useEffect(() => {
    if (hasOpenedFromQuery) {
      return;
    }

    const mediaParam = searchParams.get("media");

    if (!mediaParam || !data) {
      return;
    }

    const mediaId = Number(mediaParam);

    if (Number.isNaN(mediaId)) {
      return;
    }

    const existingItem = allItems.find((item) => item.id === mediaId);

    if (existingItem) {
      setQuerySelectedItem(null);
      setSelectedMediaId(mediaId);
      setHasOpenedFromQuery(true);
      return;
    }

    let cancelled = false;

    const openOffPageMedia = async () => {
      try {
        const media = await getImageDetail(mediaId);
        if (cancelled) {
          return;
        }
        setQuerySelectedItem(media);
        setSelectedMediaId(media.id);
        setHasOpenedFromQuery(true);
      } catch {
        if (!cancelled) {
          setHasOpenedFromQuery(true);
        }
      }
    };

    void openOffPageMedia();

    return () => {
      cancelled = true;
    };
  }, [data, allItems, searchParams, hasOpenedFromQuery]);

  const likeMutation = useMutation({
    mutationFn: (mediaId: number) => toggleLike(mediaId),
    onSuccess: ({ id }) => {
      queryClient.invalidateQueries({ queryKey: ["gallery-infinite"] });
      queryClient.invalidateQueries({ queryKey: ["image-detail", id] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (mediaId: number) => deleteImage(mediaId),
    onMutate: async (mediaId: number) => {
      setDeletionError(null);
      await queryClient.cancelQueries({ queryKey: galleryQueryKey });
      const previousData =
        queryClient.getQueryData<InfiniteData<GalleryResponse, number>>(
          galleryQueryKey,
        );

      queryClient.setQueryData<InfiniteData<GalleryResponse, number>>(
        galleryQueryKey,
        (old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.filter((item) => item.id !== mediaId),
              total: Math.max(0, page.total - 1),
            })),
          };
        },
      );

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
      queryClient.invalidateQueries({ queryKey: ["gallery-infinite"] });
    },
  });

  const reprocessMutation = useMutation({
    mutationFn: (mediaId: number) => reprocessImage(mediaId),
    onSuccess: ({ media_id }) => {
      queryClient.invalidateQueries({ queryKey: ["gallery-infinite"] });
      queryClient.invalidateQueries({ queryKey: ["image-detail", media_id] });
      toast.success("Retry queued — analysis will restart shortly.");
    },
    onError: () => {
      toast.error(
        "Retry failed. The queue may be unavailable — please try again.",
      );
    },
  });

  const moveToVaultMutation = useMutation({
    mutationFn: async (mediaId: number) => {
      if (!vaultSessionToken) {
        throw new Error("Vault session missing");
      }

      await api.post(
        "/api/vault/hide",
        { media_id: mediaId },
        {
          headers: {
            Authorization: `Bearer ${vaultSessionToken}`,
          },
        },
      );

      return mediaId;
    },
    onMutate: async (mediaId: number) => {
      await queryClient.cancelQueries({ queryKey: galleryQueryKey });

      const previousData =
        queryClient.getQueryData<InfiniteData<GalleryResponse, number>>(
          galleryQueryKey,
        );

      queryClient.setQueryData<InfiniteData<GalleryResponse, number>>(
        galleryQueryKey,
        (old) => {
          if (!old) {
            return old;
          }

          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.filter((item) => item.id !== mediaId),
              total: Math.max(0, page.total - 1),
            })),
          };
        },
      );

      if (selectedMediaId === mediaId) {
        setSelectedMediaId(null);
        setQuerySelectedItem(null);
      }

      return { previousData };
    },
    onError: (error, _mediaId, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(galleryQueryKey, context.previousData);
      }

      if (axios.isAxiosError(error) && error.response?.status === 401) {
        vaultStore.getState().lock();
        toast.error("Vault session expired");
        return;
      }

      toast.error("Failed to move to vault");
    },
    onSuccess: (mediaId) => {
      queryClient.invalidateQueries({ queryKey: ["gallery-infinite"] });
      queryClient.invalidateQueries({ queryKey: ["image-detail", mediaId] });
    },
  });

  const selectedItem = useMemo<PreviewMedia | null>(() => {
    if (selectedMediaId === null) {
      return null;
    }

    return (
      allItems.find((item) => item.id === selectedMediaId) ??
      (querySelectedItem?.id === selectedMediaId ? querySelectedItem : null)
    );
  }, [allItems, selectedMediaId, querySelectedItem]);

  const selectedIndex = useMemo(() => {
    if (selectedMediaId === null) {
      return -1;
    }
    return allItems.findIndex((item) => item.id === selectedMediaId);
  }, [allItems, selectedMediaId]);

  useEffect(() => {
    if (selectedMediaId === null) {
      return;
    }
    if (
      !allItems.some((item) => item.id === selectedMediaId) &&
      querySelectedItem?.id !== selectedMediaId
    ) {
      setSelectedMediaId(null);
    }
  }, [allItems, selectedMediaId, querySelectedItem]);

  const goToAdjacent = useCallback(
    (direction: -1 | 1) => {
      if (selectedMediaId === null) {
        return;
      }
      const currentIndex = allItems.findIndex(
        (item) => item.id === selectedMediaId,
      );
      if (currentIndex === -1) {
        return;
      }
      const next = allItems[currentIndex + direction];
      if (next) {
        setSelectedMediaId(next.id);
      }
    },
    [allItems, selectedMediaId],
  );

  const closeDetail = useCallback(() => {
    setSelectedMediaId(null);
    setQuerySelectedItem(null);

    const params = new URLSearchParams(searchParams.toString());

    params.delete("media");

    const queryString = params.toString();
    const url = queryString ? `${pathname}?${queryString}` : pathname;

    router.replace(url, { scroll: false });
  }, [router, pathname, searchParams]);

  const filters = [
    { label: "All", value: "all" },
    { label: "Indexed", value: "indexed" },
    { label: "Processing", value: "processing" },
    { label: "Failed", value: "failed" },
  ] satisfies Array<{ label: string; value: GalleryFilter }>;

  const handleLikedOnlyChange = useCallback(() => {
    updateGalleryParams({ likedOnly: !likedOnly });
  }, [likedOnly, updateGalleryParams]);

  const handleClearLikedOnly = useCallback(() => {
    updateGalleryParams({ likedOnly: false });
  }, [updateGalleryParams]);

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

  const emptyGalleryCopy = useMemo(() => {
    if (isInitialGalleryLoading || allItems.length > 0) {
      return null;
    }
    if (!data) {
      return null;
    }
    return getGalleryEmptyState(filter, likedOnly);
  }, [isInitialGalleryLoading, allItems.length, data, filter, likedOnly]);

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
              <Link
                key={value}
                href={buildGalleryHref({ filter: value })}
                scroll={false}
                aria-current={filter === value ? "page" : undefined}
                className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                  filter === value
                    ? "bg-white text-black"
                    : "text-[color:var(--silver)] hover:bg-[color:var(--frost-soft)] hover:text-[color:var(--near-white)]"
                }`}
              >
                {label}
              </Link>
            ))}
          </div>

          <button
            type="button"
            aria-pressed={likedOnly}
            onClick={handleLikedOnlyChange}
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium transition-colors ${
              likedOnly
                ? "border border-[var(--red-soft)] bg-[var(--red-soft)] text-[#ff9bab]"
                : "border border-[var(--frost)] text-[color:var(--silver)] hover:bg-[color:var(--frost-soft)] hover:text-[color:var(--near-white)]"
            }`}
          >
            <Heart className={`h-4 w-4 ${likedOnly ? "fill-current" : ""}`} />
            {likedOnly ? "Liked" : "All images"}
          </button>
        </div>

        {isInitialGalleryLoading && (
          <GallerySkeletonGrid count={GALLERY_SKELETON_COUNT} />
        )}

        {error && (
          <div className="py-32 text-center">
            <p className="text-[color:var(--silver)]">Failed to load gallery</p>
          </div>
        )}

        {emptyGalleryCopy && (
          <div className="w-full">
            <div className="frost-panel mx-auto rounded-3xl px-8 py-16 text-center">
              <ImageOff className="mx-auto mb-4 h-12 w-12 text-[color:var(--muted)]" />
              <p className="mb-2 text-[color:var(--near-white)]">
                {emptyGalleryCopy.title}
              </p>
              {emptyGalleryCopy.subtitle && (
                <p className="mb-4 text-sm text-[color:var(--silver)]">
                  {emptyGalleryCopy.subtitle}
                </p>
              )}
              {emptyGalleryCopy.showUploadLink && (
                <Link
                  href="/upload"
                  className="text-sm text-[color:var(--blue)] hover:underline"
                >
                  Upload your first images
                </Link>
              )}
              {emptyGalleryCopy.showClearLikedOnly && (
                <button
                  type="button"
                  onClick={handleClearLikedOnly}
                  className="text-sm text-[color:var(--blue)] hover:underline"
                >
                  View all images
                </button>
              )}
            </div>
          </div>
        )}

        {allItems.length > 0 && (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">
              {allItems.map((item) => {
                const imageSrc = resolveMediaUrl(
                  item.thumbnail_url ?? item.url,
                  item.minio_key,
                  item.id,
                  !item.thumbnail_url,
                );
                const originalUrl = resolveMediaUrl(item.url, item.minio_key);
                const downloadUrl = originalUrl ?? item.url ?? "";

                return (
                  <article
                    key={item.id}
                    className="frost-panel card-hover group relative overflow-hidden rounded-2xl"
                  >
                    <button
                      type="button"
                      className="relative block aspect-square w-full overflow-hidden bg-[color:var(--surface-soft)] text-left focus:outline-none"
                      onClick={() => {
                        setQuerySelectedItem(null);
                        setSelectedMediaId(item.id);
                      }}
                      aria-label={`View ${item.filename}`}
                    >
                      {imageSrc ? (
                        <GalleryThumbnail src={imageSrc} alt={item.filename} />
                      ) : (
                        <GalleryImageFallback />
                      )}

                      <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/12 to-transparent opacity-60 transition-opacity group-hover:opacity-90" />
                      <StatusIndicator
                        status={item.status}
                        className="absolute bottom-3 right-3"
                      />
                      <div className="absolute inset-0 grid place-items-center opacity-0 transition duration-200 group-hover:opacity-100">
                        <span className="icon-button h-10 w-10 bg-[color:var(--overlay)] text-white backdrop-blur-md">
                          <Eye className="h-4 w-4" />
                        </span>
                      </div>
                    </button>

                    <div className="space-y-3 p-3">
                      <p className="truncate text-xs font-medium text-[color:var(--near-white)]">
                        {item.filename}
                      </p>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleToggleLike(item.id)}
                          disabled={likeMutation.isPending}
                          className={`icon-button h-8 w-8 ${
                            item.liked
                              ? "border-[var(--red)] bg-[var(--red-soft)] text-[color:var(--red)]"
                              : "text-[color:var(--silver)]"
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
                            className="icon-button h-8 w-8 text-[color:var(--silver)]"
                            aria-label="Download image"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </a>
                        )}
                        {(item.status === "failed" ||
                          (item.status === "indexed" && !item.caption)) && (
                          <button
                            type="button"
                            onClick={() => reprocessMutation.mutate(item.id)}
                            disabled={
                              reprocessMutation.isPending &&
                              reprocessMutation.variables === item.id
                            }
                            className={`icon-button h-8 w-8 text-[color:var(--silver)] ${
                              reprocessMutation.isPending &&
                              reprocessMutation.variables === item.id
                                ? "cursor-not-allowed opacity-70"
                                : ""
                            }`}
                            aria-label="Retry analysis"
                          >
                            <RotateCcw
                              className={`h-3.5 w-3.5 ${
                                reprocessMutation.isPending &&
                                reprocessMutation.variables === item.id
                                  ? "animate-spin"
                                  : ""
                              }`}
                            />
                          </button>
                        )}
                        {isVaultUnlocked && vaultSessionToken && (
                          <button
                            type="button"
                            onClick={() => moveToVaultMutation.mutate(item.id)}
                            disabled={
                              moveToVaultMutation.isPending &&
                              moveToVaultMutation.variables === item.id
                            }
                            className={`icon-button h-8 w-8 text-[color:var(--silver)] ${
                              moveToVaultMutation.isPending &&
                              moveToVaultMutation.variables === item.id
                                ? "cursor-not-allowed opacity-70"
                                : ""
                            }`}
                            aria-label="Move to Vault"
                            title="Move to Vault"
                          >
                            <Lock className="h-3.5 w-3.5" />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() =>
                            handleDeleteRequest(item.id, item.filename)
                          }
                          disabled={deleteMutation.isPending}
                          className={`icon-button h-8 w-8 text-[color:var(--silver)] ${
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
              {Array.from(
                { length: loadingMoreSkeletonCount },
                (_, index) => (
                  <GalleryCardSkeleton key={`gallery-loading-more-${index}`} />
                ),
              )}
            </div>

            {/* Load More */}
            {hasNextPage && (
              <div className="mt-12 flex flex-col items-center gap-2">
                <button
                  type="button"
                  onClick={() => void fetchNextPage()}
                  disabled={isFetchingNextPage}
                  className="frost-button inline-flex items-center gap-2 px-6 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isFetchingNextPage ? "Loading more…" : "Load more"}
                </button>
                <p className="text-xs text-[color:var(--silver)]">
                  Showing {allItems.length} of {total}
                </p>
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
          hasNext={selectedIndex >= 0 && selectedIndex < allItems.length - 1}
          onDeleted={(mediaId) => {
            if (selectedMediaId === mediaId) {
              setSelectedMediaId(null);
              setQuerySelectedItem(null);
            }
          }}
        />
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 px-4 backdrop-blur-lg">
          <div className="frost-panel page-enter w-full max-w-sm rounded-3xl p-6">
            <h2 className="text-lg font-semibold text-[color:var(--near-white)]">
              Delete image?
            </h2>
            <p className="mt-2 text-sm text-[color:var(--silver)]">
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

/**
 * Main entry point for the Gallery route. Wraps the gallery content in a Suspense
 * boundary to support useSearchParams() during server-side rendering.
 */
export default function GalleryPage() {
  return (
    <Suspense fallback={null}>
      <GalleryPageContent />
    </Suspense>
  );
}
