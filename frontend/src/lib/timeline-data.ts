/**
 * Timeline data composition (pure, no React).
 *
 * Bridges the columnar `/timeline/bucket` API shape to the row-oriented objects
 * the justified grid + viewer consume, and composes a set of loaded buckets
 * into a single ordered flat list. Kept pure so the index math (which bucket a
 * grid position belongs to, dedupe, ordering) is unit-testable independently of
 * the React data hook that drives fetching.
 */

import type { TimelineBucket, TimelineBucketAssets } from "@/lib/api";

export interface TimelineAsset {
  id: number;
  /** Aspect ratio (w/h) for the justified layout; null when unknown. */
  ratio: number | null;
  thumbhash: string | null;
  liked: boolean;
  createdAt: string | null;
  thumbnailUrl: string;
  /** The bucket (month key) this asset belongs to. */
  timeBucket: string;
}

/**
 * Expand one columnar bucket response into per-asset objects (index-aligned
 * parallel arrays → list of objects). Tolerates short/missing arrays.
 */
export function expandBucket(bucket: TimelineBucketAssets): TimelineAsset[] {
  const ids = bucket.id ?? [];
  return ids.map((id, i) => ({
    id,
    ratio: bucket.ratio?.[i] ?? null,
    thumbhash: bucket.thumbhash?.[i] ?? null,
    liked: bucket.liked?.[i] ?? false,
    createdAt: bucket.createdAt?.[i] ?? null,
    thumbnailUrl: bucket.thumbnailUrl?.[i] ?? `/api/image/${id}/thumbnail`,
    timeBucket: bucket.timeBucket,
  }));
}

/**
 * Compose loaded buckets into one ordered, de-duplicated flat list, following
 * the order of `bucketOrder` (the order returned by `/timeline/buckets`).
 * Buckets not yet loaded are simply skipped (their assets appear once fetched).
 */
export function composeTimeline(
  bucketOrder: TimelineBucket[],
  loaded: Record<string, TimelineBucketAssets>,
): TimelineAsset[] {
  const out: TimelineAsset[] = [];
  const seen = new Set<number>();
  for (const bucket of bucketOrder) {
    const data = loaded[bucket.timeBucket];
    if (!data) {
      continue;
    }
    for (const asset of expandBucket(data)) {
      if (seen.has(asset.id)) {
        continue;
      }
      seen.add(asset.id);
      out.push(asset);
    }
  }
  return out;
}

/**
 * Total asset count across all buckets (from the cheap counts response), used
 * to size the scrollbar/scrubber before any bucket is loaded.
 */
export function totalAssetCount(bucketOrder: TimelineBucket[]): number {
  return bucketOrder.reduce((sum, b) => sum + b.count, 0);
}

/**
 * Given the bucket order and a target month key, return the keys that should
 * be loaded to display it plus a small look-ahead window (the target and the
 * next `lookahead` buckets). Used when the user scrubs to a date.
 */
export function bucketsToLoadAround(
  bucketOrder: TimelineBucket[],
  targetBucket: string,
  lookahead = 2,
): string[] {
  const index = bucketOrder.findIndex((b) => b.timeBucket === targetBucket);
  if (index < 0) {
    return [];
  }
  return bucketOrder
    .slice(index, index + lookahead + 1)
    .map((b) => b.timeBucket);
}
