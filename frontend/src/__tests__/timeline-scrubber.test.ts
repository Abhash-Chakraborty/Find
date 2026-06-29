/**
 * Unit tests for the pure timeline-scrubber geometry.
 *
 * Run with: pnpm vitest run src/__tests__/timeline-scrubber.test.ts
 */

import { describe, expect, it } from "vitest";
import {
  buildScrubberLayout,
  dateToOffset,
  formatBucketLabel,
  offsetToSegment,
  offsetToTrackFraction,
  type ScrubberBucketInput,
  trackFractionToOffset,
  trackFractionToSegment,
} from "@/lib/timeline-scrubber";

const buckets = (...pairs: [string, number][]): ScrubberBucketInput[] =>
  pairs.map(([timeBucket, count]) => ({ timeBucket, count }));

const OPTS = {
  targetRowHeight: 200,
  gap: 0,
  columnsPerRow: 10,
  headerHeight: 0,
};

describe("formatBucketLabel", () => {
  it("formats YYYY-MM-01 as 'Month YYYY'", () => {
    expect(formatBucketLabel("2026-03-01")).toBe("March 2026");
    expect(formatBucketLabel("2026-01-01")).toBe("January 2026");
    expect(formatBucketLabel("2025-12-01")).toBe("December 2025");
  });

  it("passes through unparseable / out-of-range input", () => {
    expect(formatBucketLabel("garbage")).toBe("garbage");
    expect(formatBucketLabel("2026-13-01")).toBe("2026-13-01");
  });
});

describe("buildScrubberLayout", () => {
  it("is empty for no buckets", () => {
    const layout = buildScrubberLayout([], OPTS);
    expect(layout.segments).toEqual([]);
    expect(layout.totalHeight).toBe(0);
  });

  it("estimates height as ceil(count/cols) rows and stacks offsets", () => {
    // 20 photos / 10 cols = 2 rows * 200px = 400; 5 photos => 1 row = 200.
    const layout = buildScrubberLayout(
      buckets(["2026-03-01", 20], ["2026-02-01", 5]),
      OPTS,
    );
    expect(layout.segments[0]!.height).toBe(400);
    expect(layout.segments[0]!.offsetTop).toBe(0);
    expect(layout.segments[1]!.height).toBe(200);
    expect(layout.segments[1]!.offsetTop).toBe(400);
    expect(layout.totalHeight).toBe(600);
  });

  it("gives an empty month at least one row of height", () => {
    const layout = buildScrubberLayout(buckets(["2026-03-01", 0]), OPTS);
    expect(layout.segments[0]!.height).toBe(200);
  });

  it("includes header height per segment", () => {
    const layout = buildScrubberLayout(buckets(["2026-03-01", 10]), {
      ...OPTS,
      headerHeight: 48,
    });
    // 1 row * 200 + 48 header
    expect(layout.segments[0]!.height).toBe(248);
  });

  it("preserves input order and attaches labels", () => {
    const layout = buildScrubberLayout(
      buckets(["2026-03-01", 1], ["2026-01-01", 1]),
      OPTS,
    );
    expect(layout.segments.map((s) => s.label)).toEqual([
      "March 2026",
      "January 2026",
    ]);
  });
});

describe("offset <-> segment/date mapping", () => {
  const layout = buildScrubberLayout(
    buckets(["2026-03-01", 20], ["2026-02-01", 5], ["2026-01-01", 10]),
    OPTS,
  );
  // heights: 400, 200, 200 ; offsets: 0, 400, 600 ; total 800

  it("maps an offset to the containing segment", () => {
    expect(offsetToSegment(layout, 0)?.timeBucket).toBe("2026-03-01");
    expect(offsetToSegment(layout, 399)?.timeBucket).toBe("2026-03-01");
    expect(offsetToSegment(layout, 400)?.timeBucket).toBe("2026-02-01");
    expect(offsetToSegment(layout, 599)?.timeBucket).toBe("2026-02-01");
    expect(offsetToSegment(layout, 600)?.timeBucket).toBe("2026-01-01");
  });

  it("clamps out-of-range offsets to the ends", () => {
    expect(offsetToSegment(layout, -50)?.timeBucket).toBe("2026-03-01");
    expect(offsetToSegment(layout, 99999)?.timeBucket).toBe("2026-01-01");
  });

  it("returns null for an empty layout", () => {
    expect(offsetToSegment(buildScrubberLayout([], OPTS), 0)).toBeNull();
  });

  it("dateToOffset returns a segment's top, or null when missing", () => {
    expect(dateToOffset(layout, "2026-03-01")).toBe(0);
    expect(dateToOffset(layout, "2026-02-01")).toBe(400);
    expect(dateToOffset(layout, "2026-01-01")).toBe(600);
    expect(dateToOffset(layout, "2099-01-01")).toBeNull();
  });

  it("dateToOffset round-trips through offsetToSegment", () => {
    for (const seg of layout.segments) {
      const offset = dateToOffset(layout, seg.timeBucket);
      expect(offset).not.toBeNull();
      expect(offsetToSegment(layout, offset as number)?.timeBucket).toBe(
        seg.timeBucket,
      );
    }
  });
});

describe("track-fraction mapping", () => {
  const layout = buildScrubberLayout(
    buckets(["2026-03-01", 20], ["2026-02-01", 5], ["2026-01-01", 10]),
    OPTS,
  ); // total 800

  it("maps fraction to offset across the total height", () => {
    expect(trackFractionToOffset(layout, 0)).toBe(0);
    expect(trackFractionToOffset(layout, 0.5)).toBe(400);
    expect(trackFractionToOffset(layout, 1)).toBe(800);
  });

  it("clamps fraction to [0,1]", () => {
    expect(trackFractionToOffset(layout, -1)).toBe(0);
    expect(trackFractionToOffset(layout, 2)).toBe(800);
  });

  it("maps a track fraction to the hovered segment", () => {
    expect(trackFractionToSegment(layout, 0)?.timeBucket).toBe("2026-03-01");
    expect(trackFractionToSegment(layout, 0.5)?.timeBucket).toBe("2026-02-01");
    expect(trackFractionToSegment(layout, 0.99)?.timeBucket).toBe("2026-01-01");
  });

  it("offsetToTrackFraction is the inverse of trackFractionToOffset", () => {
    for (const f of [0, 0.25, 0.5, 0.75, 1]) {
      const offset = trackFractionToOffset(layout, f);
      expect(offsetToTrackFraction(layout, offset)).toBeCloseTo(f, 6);
    }
  });

  it("offsetToTrackFraction returns 0 for an empty layout", () => {
    expect(offsetToTrackFraction(buildScrubberLayout([], OPTS), 100)).toBe(0);
  });
});
