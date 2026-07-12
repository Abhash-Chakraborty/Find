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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AssetViewer } from "@/components/asset-viewer";
import { JustifiedGrid } from "@/components/justified-grid";
import { TimelineScrubber } from "@/components/timeline-scrubber";
import { setArchive, toggleLike, trashImage } from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";
import {
  buildScrubberLayout,
  offsetToSegment,
  offsetToTrackFraction,
} from "@/lib/timeline-scrubber";
import { useTimeline } from "@/lib/use-timeline";

export default function TimelinePage() {
  const queryClient = useQueryClient();
  const [likedOnly, setLikedOnly] = useState(
    () =>
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("liked") === "true",
  );
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
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  // Local favorite overrides for instant feedback (the per-bucket cache isn't
  // refetched on a like toggle, only on a filter change).
  const [favoriteOverrides, setFavoriteOverrides] = useState<
    Record<number, boolean>
  >({});
  // Assets archived/trashed from the viewer leave the grid immediately; the
  // per-bucket cache still holds them, so we hide them locally.
  const [removedIds, setRemovedIds] = useState<Set<number>>(new Set());
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  const visibleAssets = useMemo(
    () => assets.filter((a) => !removedIds.has(a.id)),
    [assets, removedIds],
  );

  const favoriteIds = useMemo(() => {
    const ids = new Set<number>();
    for (const a of assets) {
      const overridden = favoriteOverrides[a.id];
      if (overridden ?? a.liked) {
        ids.add(a.id);
      }
    }
    return ids;
  }, [assets, favoriteOverrides]);

  const favoriteMutation = useMutation({
    mutationFn: (mediaId: number) => toggleLike(mediaId),
    onSuccess: ({ id, liked }) => {
      setFavoriteOverrides((cur) => ({ ...cur, [id]: liked }));
      queryClient.invalidateQueries({ queryKey: ["gallery-counts"] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (mediaId: number) => setArchive(mediaId, true),
    onSuccess: ({ id }) => {
      setRemovedIds((cur) => new Set(cur).add(id));
      queryClient.invalidateQueries({ queryKey: ["archive"] });
    },
  });

  const trashMutation = useMutation({
    mutationFn: (mediaId: number) => trashImage(mediaId),
    onSuccess: ({ id }) => {
      setRemovedIds((cur) => new Set(cur).add(id));
      queryClient.invalidateQueries({ queryKey: ["trash"] });
    },
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
      { rootMargin: "800px 0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadBucket, nextBucket]);

  // When the user scrubs: load the target month's data AND scroll the grid to
  // it. The scrubber works in estimated-height space and the grid in real
  // layout space, so we bridge via a 0..1 fraction → window scroll position.
  const scrubberLayout = useMemo(() => buildScrubberLayout(buckets), [buckets]);

  useEffect(() => {
    if (typeof window === "undefined" || scrubberLayout.totalHeight <= 0) {
      return;
    }
    const update = () => {
      const documentElement = document.documentElement;
      const scrollable = Math.max(
        1,
        documentElement.scrollHeight - window.innerHeight,
      );
      const fraction = Math.min(1, Math.max(0, window.scrollY / scrollable));
      const offset = fraction * scrubberLayout.totalHeight;
      setScrollOffset(offset);
      const segment = offsetToSegment(scrubberLayout, offset);
      if (segment) loadBucket(segment.timeBucket);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, [loadBucket, scrubberLayout]);
  const handleScrub = useCallback(
    (offset: number) => {
      setScrollOffset(offset);
      const segment = offsetToSegment(scrubberLayout, offset);
      if (segment) {
        loadBucket(segment.timeBucket);
      }
      if (typeof window !== "undefined") {
        const fraction = offsetToTrackFraction(scrubberLayout, offset);
        const doc = document.documentElement;
        const scrollable = Math.max(0, doc.scrollHeight - window.innerHeight);
        window.scrollTo({ top: fraction * scrollable, behavior: "auto" });
      }
    },
    [scrubberLayout, loadBucket],
  );

  const viewerAssets = visibleAssets.map((a) => ({
    id: a.id,
    thumbnailUrl:
      resolveMediaUrl(a.thumbnailUrl, null, a.id, true) ?? a.thumbnailUrl,
    originalUrl:
      resolveMediaUrl(`/api/image/${a.id}/original`) ??
      `/api/image/${a.id}/original`,
    alt: a.createdAt
      ? `Photo from ${new Date(a.createdAt).toLocaleDateString()}`
      : `Photo ${a.id}`,
  }));

  return (
    <main
      className="timeline-page page-surface"
      style={{ position: "relative" }}
    >
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-[var(--frost)] pb-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--blue)]">
            Library
          </p>
          <h1 className="mt-1 text-3xl font-semibold text-[color:var(--near-white)]">
            Photos
          </h1>
          {!isLoadingBuckets && (
            <p
              data-testid="timeline-total"
              className="mt-1 text-sm text-[color:var(--silver)]"
            >
              {total} photos
            </p>
          )}
        </div>
        <button
          type="button"
          data-testid="timeline-favorites-toggle"
          aria-pressed={likedOnly}
          onClick={() =>
            setLikedOnly((current) => {
              const next = !current;
              if (typeof window !== "undefined") {
                const url = new URL(window.location.href);
                if (next) url.searchParams.set("liked", "true");
                else url.searchParams.delete("liked");
                window.history.replaceState(null, "", url);
              }
              return next;
            })
          }
          className="frost-button px-4 py-2 text-sm font-medium"
        >
          {likedOnly ? "Showing favorites" : "Show favorites"}
        </button>
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

      <div className="flex gap-3" style={{ display: "flex" }}>
        <div ref={scrollRef} id="timeline-scroll-region" style={{ flex: 1 }}>
          <JustifiedGrid
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
            className="grid min-h-16 place-items-center text-xs text-[color:var(--muted)]"
            aria-live="polite"
          >
            {nextBucket ? "Loading more of your timeline…" : null}
          </div>
        </div>

        {buckets.length > 0 && (
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

      {viewerIndex !== null && viewerAssets[viewerIndex] && (
        <AssetViewer
          assets={viewerAssets}
          index={viewerIndex}
          onIndexChange={setViewerIndex}
          onClose={() => setViewerIndex(null)}
          favoriteIds={favoriteIds}
          onToggleFavorite={(id) => favoriteMutation.mutate(id)}
          onArchive={(id) => archiveMutation.mutate(id)}
          onTrash={(id) => trashMutation.mutate(id)}
        />
      )}
    </main>
  );
}
