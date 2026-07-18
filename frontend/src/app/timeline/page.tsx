"use client";

/**
 * Timeline page — the reference-grade browsing surface, wiring the Phase 3
 * pieces together against the live timeline API:
 *   useTimeline (data)  →  JustifiedGrid (layout)  +  TimelineScrubber (date nav)
 *                          +  AssetViewer (full-screen zoom/pan/slideshow).
 *
 * All heavy logic lives in unit-tested modules; this page owns composition and
 * the small amount of view state (scroll offset, viewer open index).
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";
import { ImagePreviewModal } from "@/components/image-preview-modal";
import { JustifiedGrid } from "@/components/justified-grid";
import { TimelineScrubber } from "@/components/timeline-scrubber";
import { setArchive, trashImage } from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";
import {
  buildScrubberLayout,
  offsetToSegment,
  offsetToTrackFraction,
} from "@/lib/timeline-scrubber";
import { useTimeline } from "@/lib/use-timeline";

function TimelinePageContent() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const likedOnly = searchParams
    ? searchParams.get("liked") === "true"
    : typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("liked") === "true";
  const {
    buckets,
    assets,
    total,
    isLoadingBuckets,
    isError,
    loadBucket,
    loadedBucketKeys,
  } = useTimeline({
    liked: likedOnly || undefined,
  });
  const [scrollOffset, setScrollOffset] = useState(0);
  const [canScroll, setCanScroll] = useState(false);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  // Assets archived/trashed from the viewer leave the grid immediately; the
  // per-bucket cache still holds them, so we hide them locally.
  const [removedIds, setRemovedIds] = useState<Set<number>>(new Set());
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  const visibleAssets = useMemo(
    () => assets.filter((a) => !removedIds.has(a.id)),
    [assets, removedIds],
  );

  const archiveMutation = useMutation({
    mutationFn: (mediaId: number) => setArchive(mediaId, true),
    onSuccess: ({ id }) => {
      setRemovedIds((cur) => new Set(cur).add(id));
      queryClient.invalidateQueries({ queryKey: ["archive"] });
    },
    onError: () => toast.error("Failed to archive photo. Please try again."),
  });

  const trashMutation = useMutation({
    mutationFn: (mediaId: number) => trashImage(mediaId),
    onSuccess: ({ id }) => {
      setRemovedIds((cur) => new Set(cur).add(id));
      queryClient.invalidateQueries({ queryKey: ["trash"] });
    },
    onError: () =>
      toast.error("Failed to move photo to trash. Please try again."),
  });

  // Once buckets are known, eagerly load the first bucket so the grid has
  // content to render immediately.
  useEffect(() => {
    const first = buckets[0];
    if (first) {
      loadBucket(first.timeBucket);
    }
  }, [buckets, loadBucket]);

  const nextBucket = useMemo(() => {
    const loaded = new Set(loadedBucketKeys);
    return buckets.find((bucket) => !loaded.has(bucket.timeBucket));
  }, [buckets, loadedBucketKeys]);

  useEffect(() => {
    const sentinel = loadMoreRef.current;
    if (
      !sentinel ||
      !nextBucket ||
      typeof IntersectionObserver === "undefined"
    ) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          loadBucket(nextBucket.timeBucket);
        }
      },
      { root: scrollRef.current, rootMargin: "800px 0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadBucket, nextBucket]);

  // When the user scrubs: load the target month's data AND scroll the grid to
  // it. The scrubber works in estimated-height space and the grid in real
  // layout space, so we bridge via a 0..1 fraction → window scroll position.
  const scrubberLayout = useMemo(() => buildScrubberLayout(buckets), [buckets]);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container || scrubberLayout.totalHeight <= 0) return;

    const update = () => {
      const scrollable = Math.max(
        0,
        container.scrollHeight - container.clientHeight,
      );
      setCanScroll(scrollable > 2);
      const fraction =
        scrollable > 0
          ? Math.min(1, Math.max(0, container.scrollTop / scrollable))
          : 0;
      const offset = fraction * scrubberLayout.totalHeight;
      setScrollOffset(offset);
      const segment = offsetToSegment(scrubberLayout, offset);
      if (segment) loadBucket(segment.timeBucket);
    };

    update();
    container.addEventListener("scroll", update, { passive: true });
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(container);
    return () => {
      container.removeEventListener("scroll", update);
      observer?.disconnect();
    };
  }, [loadBucket, scrubberLayout]);

  const visibleAssetCount = visibleAssets.length;
  useEffect(() => {
    if (visibleAssetCount === 0) {
      setCanScroll(false);
      return;
    }
    const frame = requestAnimationFrame(() => {
      const container = scrollRef.current;
      if (container) {
        setCanScroll(container.scrollHeight - container.clientHeight > 2);
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [visibleAssetCount]);
  const handleScrub = useCallback(
    (offset: number) => {
      setScrollOffset(offset);
      const segment = offsetToSegment(scrubberLayout, offset);
      if (segment) {
        loadBucket(segment.timeBucket);
      }
      const container = scrollRef.current;
      if (container) {
        const fraction = offsetToTrackFraction(scrubberLayout, offset);
        const scrollable = Math.max(
          0,
          container.scrollHeight - container.clientHeight,
        );
        container.scrollTo({ top: fraction * scrollable, behavior: "auto" });
      }
    },
    [scrubberLayout, loadBucket],
  );
  const activeViewerAsset =
    viewerIndex === null ? null : (visibleAssets[viewerIndex] ?? null);

  return (
    <main
      className="timeline-page page-surface flex h-[calc(100dvh-var(--nav-height))] flex-col overflow-hidden pt-6 sm:pt-8"
      style={{ position: "relative" }}
    >
      <header className="mb-4 shrink-0 border-b border-[var(--frost)] pb-4">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-sm font-semibold text-[color:var(--blue)]">
            Library
          </span>
          <span aria-hidden="true" className="text-[color:var(--muted)]">
            /
          </span>
          <h1 className="text-3xl font-semibold text-[color:var(--near-white)]">
            {likedOnly ? "Favorites" : "Photos"}
          </h1>
          {!isLoadingBuckets && (
            <p
              data-testid="timeline-total"
              className="ml-1 text-sm text-[color:var(--silver)]"
            >
              {total} photos
            </p>
          )}
        </div>
      </header>

      {isLoadingBuckets && (
        <div role="status" aria-label="Loading timeline">
          Loading timeline…
        </div>
      )}

      {!isLoadingBuckets && isError && (
        <p data-testid="timeline-error" role="alert">
          Couldn't load the timeline. Please try again.
        </p>
      )}

      {!isLoadingBuckets && !isError && total === 0 && (
        <p data-testid="timeline-empty">No photos yet.</p>
      )}

      <div className="flex min-h-0 flex-1 gap-3">
        <div
          ref={scrollRef}
          id="timeline-scroll-region"
          className="timeline-native-scroll min-w-0 flex-1 overflow-y-auto pr-1"
        >
          <JustifiedGrid
            scrollContainerRef={scrollRef}
            items={visibleAssets}
            getKey={(a) => a.id}
            renderItem={(asset, index) => (
              <button
                type="button"
                data-testid={`timeline-cell-${asset.id}`}
                onClick={() => setViewerIndex(index)}
                style={{ width: "100%", height: "100%", padding: 0, border: 0 }}
              >
                {/* biome-ignore lint/performance/noImgElement: authenticated API thumbnail */}
                <img
                  src={
                    resolveMediaUrl(asset.thumbnailUrl, null, asset.id, true) ??
                    asset.thumbnailUrl
                  }
                  alt={
                    asset.createdAt
                      ? `Photo from ${new Date(asset.createdAt).toLocaleDateString()}`
                      : `Photo ${asset.id}`
                  }
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              </button>
            )}
          />
          <div
            ref={loadMoreRef}
            className="grid min-h-8 place-items-center text-xs text-[color:var(--muted)]"
            aria-live="polite"
          >
            {nextBucket ? "Loading more of your timeline…" : null}
          </div>
        </div>

        {canScroll && buckets.length > 1 && (
          <aside
            aria-label="Timeline navigation"
            className="sticky top-[calc(var(--nav-height)+12px)] h-[calc(100dvh-var(--nav-height)-24px)] text-[color:var(--silver)]"
          >
            <TimelineScrubber
              buckets={buckets}
              scrollOffset={scrollOffset}
              onScrub={handleScrub}
            />
          </aside>
        )}
      </div>

      {viewerIndex !== null && activeViewerAsset && (
        <ImagePreviewModal
          media={{
            id: activeViewerAsset.id,
            filename: `Photo ${activeViewerAsset.id}`,
            created_at: activeViewerAsset.createdAt ?? undefined,
            liked: activeViewerAsset.liked,
          }}
          onClose={() => setViewerIndex(null)}
          onPrevious={() =>
            setViewerIndex((current) => (current === null ? null : current - 1))
          }
          onNext={() =>
            setViewerIndex((current) => (current === null ? null : current + 1))
          }
          hasPrevious={viewerIndex > 0}
          hasNext={viewerIndex < visibleAssets.length - 1}
          onDeleted={(id) =>
            setRemovedIds((current) => new Set(current).add(id))
          }
          actions={
            <>
              <button
                type="button"
                data-testid="preview-archive"
                className="frost-button px-4 py-2 text-sm"
                onClick={() => {
                  archiveMutation.mutate(activeViewerAsset.id);
                  setViewerIndex(null);
                }}
              >
                <Archive className="h-4 w-4" /> Archive
              </button>
              <button
                type="button"
                data-testid="preview-trash"
                className="frost-button px-4 py-2 text-sm"
                onClick={() => {
                  trashMutation.mutate(activeViewerAsset.id);
                  setViewerIndex(null);
                }}
              >
                <Trash2 className="h-4 w-4" /> Move to trash
              </button>
            </>
          }
        />
      )}
    </main>
  );
}

export default function TimelinePage() {
  return (
    <Suspense
      fallback={
        <main className="timeline-page page-surface h-[calc(100dvh-var(--nav-height))] animate-pulse" />
      }
    >
      <TimelinePageContent />
    </Suspense>
  );
}
