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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { JustifiedGrid } from "@/components/justified-grid";
import { TimelineScrubber } from "@/components/timeline-scrubber";
import { AssetViewer } from "@/components/asset-viewer";
import { toggleLike } from "@/lib/api";
import { useTimeline } from "@/lib/use-timeline";
import { buildScrubberLayout, offsetToSegment } from "@/lib/timeline-scrubber";

export default function TimelinePage() {
  const queryClient = useQueryClient();
  const [likedOnly, setLikedOnly] = useState(false);
  const { buckets, assets, total, isLoadingBuckets, loadBucket } = useTimeline({
    liked: likedOnly || undefined,
  });
  const [scrollOffset, setScrollOffset] = useState(0);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  // Local favorite overrides for instant feedback (the per-bucket cache isn't
  // refetched on a like toggle, only on a filter change).
  const [favoriteOverrides, setFavoriteOverrides] = useState<
    Record<number, boolean>
  >({});
  const scrollRef = useRef<HTMLDivElement | null>(null);

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

  // Once buckets are known, eagerly load the first bucket so the grid has
  // content to render immediately.
  useEffect(() => {
    const first = buckets[0];
    if (first) {
      loadBucket(first.timeBucket);
    }
  }, [buckets, loadBucket]);

  // When the user scrubs, map the offset to a month and ensure it's loaded.
  const scrubberLayout = buildScrubberLayout(buckets);
  const handleScrub = useCallback(
    (offset: number) => {
      setScrollOffset(offset);
      const segment = offsetToSegment(scrubberLayout, offset);
      if (segment) {
        loadBucket(segment.timeBucket);
      }
    },
    [scrubberLayout, loadBucket],
  );

  const viewerAssets = assets.map((a) => ({
    id: a.id,
    thumbnailUrl: a.thumbnailUrl,
    originalUrl: `/api/image/${a.id}`,
  }));

  return (
    <main className="timeline-page" style={{ position: "relative" }}>
      <header>
        <h1>Timeline</h1>
        {!isLoadingBuckets && (
          <p data-testid="timeline-total">{total} photos</p>
        )}
        <button
          type="button"
          data-testid="timeline-favorites-toggle"
          aria-pressed={likedOnly}
          onClick={() => setLikedOnly((v) => !v)}
        >
          {likedOnly ? "Showing favorites" : "Show favorites"}
        </button>
      </header>

      {isLoadingBuckets && (
        <div role="status" aria-label="Loading timeline">
          Loading timeline…
        </div>
      )}

      {!isLoadingBuckets && total === 0 && (
        <p data-testid="timeline-empty">No photos yet.</p>
      )}

      <div style={{ display: "flex" }}>
        <div ref={scrollRef} style={{ flex: 1 }}>
          <JustifiedGrid
            items={assets}
            getKey={(a) => a.id}
            renderItem={(asset, index) => (
              <button
                type="button"
                data-testid={`timeline-cell-${asset.id}`}
                onClick={() => setViewerIndex(index)}
                style={{ width: "100%", height: "100%", padding: 0, border: 0 }}
              >
                {/* biome-ignore lint/a11y/useAltText: thumbnail tile */}
                <img
                  src={asset.thumbnailUrl}
                  alt=""
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              </button>
            )}
          />
        </div>

        {buckets.length > 0 && (
          <TimelineScrubber
            buckets={buckets}
            scrollOffset={scrollOffset}
            onScrub={handleScrub}
          />
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
        />
      )}
    </main>
  );
}
