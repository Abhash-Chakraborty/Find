import { describe, expect, it } from "vitest";
import {
  actualOffsetToScrubberOffset,
  groupMediaByMonth,
  mediaAspectRatio,
  scrubberOffsetToActualOffset,
  timelineBucketsFromGroups,
} from "@/lib/media-timeline";
import { buildScrubberLayout } from "@/lib/timeline-scrubber";

interface Item {
  id: number;
  createdAt: string | null;
}

describe("media timeline grouping", () => {
  it("groups and orders media newest-first while retaining undated items", () => {
    const items: Item[] = [
      { id: 1, createdAt: "2026-02-01T00:00:00Z" },
      { id: 2, createdAt: "2026-03-02T00:00:00Z" },
      { id: 3, createdAt: "2026-03-20T00:00:00Z" },
      { id: 4, createdAt: null },
    ];

    const groups = groupMediaByMonth(items, (item) => item.createdAt);

    expect(groups.map((group) => group.timeBucket)).toEqual([
      "2026-03-01",
      "2026-02-01",
      "undated",
    ]);
    expect(groups[0]?.items.map((item) => item.id)).toEqual([3, 2]);
    expect(groups[2]?.label).toBe("Undated");
    expect(timelineBucketsFromGroups(groups)).toEqual([
      { timeBucket: "2026-03-01", count: 2 },
      { timeBucket: "2026-02-01", count: 1 },
      { timeBucket: "undated", count: 1 },
    ]);
  });

  it("uses a safe square ratio when dimensions are unusable", () => {
    expect(mediaAspectRatio(1600, 800)).toBe(2);
    expect(mediaAspectRatio(null, 800)).toBe(1);
    expect(mediaAspectRatio(100, 0)).toBe(1);
  });
});

describe("media timeline scroll mapping", () => {
  const buckets = [
    { timeBucket: "2026-03-01", count: 5 },
    { timeBucket: "2026-02-01", count: 2 },
  ];
  const layout = buildScrubberLayout(buckets, {
    columnsPerRow: 5,
    gap: 0,
    headerHeight: 0,
    targetRowHeight: 100,
  });
  const measurements = [
    { timeBucket: "2026-03-01", top: 0, height: 300 },
    { timeBucket: "2026-02-01", top: 300, height: 100 },
  ];

  it("keeps within-month progress when mapping real scroll to the scrubber", () => {
    expect(actualOffsetToScrubberOffset(measurements, layout, 150)).toBe(50);
    expect(actualOffsetToScrubberOffset(measurements, layout, 350)).toBe(150);
  });

  it("maps scrubber positions back to real rendered sections", () => {
    expect(scrubberOffsetToActualOffset(measurements, layout, 50)).toBe(150);
    expect(scrubberOffsetToActualOffset(measurements, layout, 150)).toBe(350);
  });
});
