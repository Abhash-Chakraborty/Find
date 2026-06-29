"use client";

/**
 * useTimeline — drives the timeline data flow for the gallery page.
 *
 * Thin React/react-query glue over the unit-tested pure helpers in
 * `@/lib/timeline-data`:
 *  - loads the cheap month-bucket counts once (sizes the scrubber),
 *  - lazily fetches per-bucket assets as buckets are requested,
 *  - composes loaded buckets into one ordered flat list for the grid.
 *
 * The composition/index logic lives in timeline-data.ts (tested separately);
 * this hook only owns fetch orchestration + cache state.
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getTimelineBucket,
  getTimelineBuckets,
  type SortOrder,
  type TimelineBucketAssets,
} from "@/lib/api";
import {
  composeTimeline,
  type TimelineAsset,
  totalAssetCount,
} from "@/lib/timeline-data";

export interface UseTimelineResult {
  buckets: { timeBucket: string; count: number }[];
  assets: TimelineAsset[];
  total: number;
  isLoadingBuckets: boolean;
  /** True when the bucket-counts query failed. */
  isError: boolean;
  /** Ensure a bucket's assets are loaded (idempotent). */
  loadBucket: (timeBucket: string) => void;
  loadedBucketKeys: string[];
}

export function useTimeline(
  options: { order?: SortOrder; liked?: boolean } = {},
): UseTimelineResult {
  const order = options.order ?? "newest";
  const liked = options.liked;

  const {
    data: bucketData,
    isLoading: isLoadingBuckets,
    isError,
  } = useQuery({
    queryKey: ["timeline-buckets", order, liked ?? null],
    queryFn: () => getTimelineBuckets({ order, liked }),
  });

  const bucketOrder = useMemo(() => bucketData?.buckets ?? [], [bucketData]);

  // Loaded per-bucket asset payloads, keyed by month.
  const [loaded, setLoaded] = useState<Record<string, TimelineBucketAssets>>(
    {},
  );
  // Which buckets we've requested (prevents duplicate fetches). Only the
  // setter is read; the set is inspected via the updater's `prev`.
  const [, setRequested] = useState<Set<string>>(new Set());

  // When the filter params change (order/liked), previously-loaded buckets are
  // stale (they hold assets for the OLD filter), so clear the per-bucket cache.
  // Without this, toggling favorites keeps showing the unfiltered assets for
  // any month already loaded.
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset keyed on filter params
  useEffect(() => {
    setLoaded({});
    setRequested(new Set());
  }, [order, liked]);

  const loadBucket = useCallback(
    (timeBucket: string) => {
      setRequested((prev) => {
        if (prev.has(timeBucket)) {
          return prev;
        }
        const next = new Set(prev);
        next.add(timeBucket);
        // Fire the fetch outside the state updater.
        getTimelineBucket({ timeBucket, order, liked })
          .then((payload) =>
            setLoaded((cur) => ({ ...cur, [timeBucket]: payload })),
          )
          .catch(() => {
            // On failure, drop from requested so it can be retried.
            setRequested((r) => {
              const back = new Set(r);
              back.delete(timeBucket);
              return back;
            });
          });
        return next;
      });
    },
    [order, liked],
  );

  const assets = useMemo(
    () => composeTimeline(bucketOrder, loaded),
    [bucketOrder, loaded],
  );

  const total = useMemo(() => totalAssetCount(bucketOrder), [bucketOrder]);

  return {
    buckets: bucketOrder,
    assets,
    total,
    isLoadingBuckets,
    isError,
    loadBucket,
    loadedBucketKeys: Object.keys(loaded),
  };
}
