/**
 * Unit tests for the pure timeline data composition.
 *
 * Run with: pnpm vitest run src/__tests__/timeline-data.test.ts
 */

import { describe, expect, it } from "vitest";
import type { TimelineBucket, TimelineBucketAssets } from "@/lib/api";
import {
  bucketsToLoadAround,
  composeTimeline,
  expandBucket,
  totalAssetCount,
} from "@/lib/timeline-data";

function bucketAssets(
  timeBucket: string,
  ids: number[],
  overrides: Partial<TimelineBucketAssets> = {},
): TimelineBucketAssets {
  return {
    timeBucket,
    count: ids.length,
    id: ids,
    ratio: ids.map(() => 1.5),
    thumbhash: ids.map(() => null),
    liked: ids.map(() => false),
    createdAt: ids.map(() => "2026-03-01T00:00:00+00:00"),
    thumbnailUrl: ids.map((id) => `/api/image/${id}/thumbnail`),
    ...overrides,
  };
}

const order = (...pairs: [string, number][]): TimelineBucket[] =>
  pairs.map(([timeBucket, count]) => ({ timeBucket, count }));

describe("expandBucket", () => {
  it("maps columnar arrays to per-asset objects in order", () => {
    const assets = expandBucket(bucketAssets("2026-03-01", [10, 20, 30]));
    expect(assets.map((a) => a.id)).toEqual([10, 20, 30]);
    expect(assets[0]!.timeBucket).toBe("2026-03-01");
    expect(assets[0]!.ratio).toBe(1.5);
    expect(assets[0]!.thumbnailUrl).toBe("/api/image/10/thumbnail");
  });

  it("tolerates missing/short parallel arrays with safe defaults", () => {
    const partial: TimelineBucketAssets = {
      timeBucket: "2026-03-01",
      count: 2,
      id: [1, 2],
      ratio: [2.0], // short
      thumbhash: [],
      liked: [],
      createdAt: [],
      thumbnailUrl: [],
    };
    const assets = expandBucket(partial);
    expect(assets).toHaveLength(2);
    expect(assets[0]!.ratio).toBe(2.0);
    expect(assets[1]!.ratio).toBeNull();
    expect(assets[1]!.liked).toBe(false);
    // Falls back to a derived thumbnail URL when none supplied.
    expect(assets[1]!.thumbnailUrl).toBe("/api/image/2/thumbnail");
  });

  it("returns empty for an empty bucket", () => {
    expect(expandBucket(bucketAssets("2026-03-01", []))).toEqual([]);
  });
});

describe("composeTimeline", () => {
  it("flattens loaded buckets in the bucket order", () => {
    const ord = order(["2026-03-01", 2], ["2026-02-01", 1]);
    const loaded = {
      "2026-03-01": bucketAssets("2026-03-01", [1, 2]),
      "2026-02-01": bucketAssets("2026-02-01", [3]),
    };
    expect(composeTimeline(ord, loaded).map((a) => a.id)).toEqual([1, 2, 3]);
  });

  it("skips buckets not yet loaded (no gaps, just absent)", () => {
    const ord = order(["2026-03-01", 2], ["2026-02-01", 1], ["2026-01-01", 1]);
    const loaded = {
      "2026-03-01": bucketAssets("2026-03-01", [1, 2]),
      "2026-01-01": bucketAssets("2026-01-01", [9]),
    };
    // Middle bucket absent → its assets simply don't appear yet.
    expect(composeTimeline(ord, loaded).map((a) => a.id)).toEqual([1, 2, 9]);
  });

  it("de-duplicates assets that appear in more than one loaded bucket", () => {
    const ord = order(["2026-03-01", 2], ["2026-02-01", 2]);
    const loaded = {
      "2026-03-01": bucketAssets("2026-03-01", [1, 2]),
      "2026-02-01": bucketAssets("2026-02-01", [2, 3]), // 2 repeated
    };
    expect(composeTimeline(ord, loaded).map((a) => a.id)).toEqual([1, 2, 3]);
  });

  it("is empty when nothing is loaded", () => {
    expect(composeTimeline(order(["2026-03-01", 2]), {})).toEqual([]);
  });
});

describe("totalAssetCount", () => {
  it("sums counts across buckets", () => {
    expect(totalAssetCount(order(["a", 3], ["b", 5], ["c", 0]))).toBe(8);
  });

  it("is zero for no buckets", () => {
    expect(totalAssetCount([])).toBe(0);
  });
});

describe("bucketsToLoadAround", () => {
  const ord = order(
    ["2026-05-01", 1],
    ["2026-04-01", 1],
    ["2026-03-01", 1],
    ["2026-02-01", 1],
  );

  it("returns the target plus a lookahead window", () => {
    expect(bucketsToLoadAround(ord, "2026-04-01", 2)).toEqual([
      "2026-04-01",
      "2026-03-01",
      "2026-02-01",
    ]);
  });

  it("clamps the window at the end of the list", () => {
    expect(bucketsToLoadAround(ord, "2026-02-01", 2)).toEqual(["2026-02-01"]);
  });

  it("returns empty for an unknown target", () => {
    expect(bucketsToLoadAround(ord, "1999-01-01")).toEqual([]);
  });

  it("loads only the target with lookahead 0", () => {
    expect(bucketsToLoadAround(ord, "2026-04-01", 0)).toEqual(["2026-04-01"]);
  });
});
