/**
 * Timeline date-scrubber geometry (pure, no React).
 *
 * The scrubber is the fast date-scrollbar on the right edge of the timeline.
 * It needs to know each month's pixel height *before* the justified grid lays
 * out, so heights are estimated from bucket counts. This module turns the
 * bucket-count contract (`GET /timeline/buckets`) into:
 *
 *  - per-segment estimated heights + cumulative scroll offsets (total height),
 *  - scroll-offset <-> date mapping (floating label while scrubbing, jump-to),
 *  - track-fraction <-> segment mapping (hover preview on the thin track).
 *
 * Estimation mirrors the justified grid: a month of N photos at an assumed
 * columns-per-row C occupies ceil(N / C) rows of (rowHeight + gap), plus a
 * month header. It is intentionally approximate — the grid is the source of
 * truth for real positions; the scrubber only needs to feel right.
 *
 * Adapted from the AGPL-3.0 reference project's timeline scrubber behavior
 * (Immich). Original © its authors. Part of Find, distributed under AGPL-3.0.
 */

export interface ScrubberBucketInput {
  /** Month key "YYYY-MM-01" (or any "YYYY-MM..."). */
  timeBucket: string;
  count: number;
}

export interface ScrubberSegment {
  timeBucket: string;
  count: number;
  /** Estimated pixel height of this month's section in the timeline. */
  height: number;
  /** Cumulative pixel offset of this segment's top within the timeline. */
  offsetTop: number;
  /** Human label, e.g. "March 2026". */
  label: string;
}

export interface ScrubberLayout {
  segments: ScrubberSegment[];
  /** Total estimated timeline height in px. */
  totalHeight: number;
}

export interface ScrubberOptions {
  targetRowHeight?: number;
  gap?: number;
  /** Assumed photos per row used only for height estimation. */
  columnsPerRow?: number;
  /** Pixel height reserved for each month's header/label row. */
  headerHeight?: number;
}

const DEFAULT_TARGET_ROW_HEIGHT = 235;
const DEFAULT_GAP = 8;
const DEFAULT_COLUMNS_PER_ROW = 5;
const DEFAULT_HEADER_HEIGHT = 48;

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** Format a "YYYY-MM-01" bucket key as "Month YYYY"; pass through if unparseable. */
export function formatBucketLabel(timeBucket: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(timeBucket.trim());
  if (!match) {
    return timeBucket;
  }
  const year = Number.parseInt(match[1] as string, 10);
  const month = Number.parseInt(match[2] as string, 10);
  if (month < 1 || month > 12) {
    return timeBucket;
  }
  return `${MONTH_NAMES[month - 1] ?? ""} ${year}`;
}

function estimateSegmentHeight(
  count: number,
  opts: Required<ScrubberOptions>,
): number {
  const rows = Math.max(1, Math.ceil(count / opts.columnsPerRow));
  return opts.headerHeight + rows * (opts.targetRowHeight + opts.gap);
}

/**
 * Build the scrubber layout from bucket counts. Preserves the input order
 * (callers pass buckets already ordered newest- or oldest-first).
 */
export function buildScrubberLayout(
  buckets: ScrubberBucketInput[],
  options: ScrubberOptions = {},
): ScrubberLayout {
  const opts: Required<ScrubberOptions> = {
    targetRowHeight: options.targetRowHeight ?? DEFAULT_TARGET_ROW_HEIGHT,
    gap: options.gap ?? DEFAULT_GAP,
    columnsPerRow: options.columnsPerRow ?? DEFAULT_COLUMNS_PER_ROW,
    headerHeight: options.headerHeight ?? DEFAULT_HEADER_HEIGHT,
  };

  const segments: ScrubberSegment[] = [];
  let offsetTop = 0;
  for (const bucket of buckets) {
    const height = estimateSegmentHeight(Math.max(0, bucket.count), opts);
    segments.push({
      timeBucket: bucket.timeBucket,
      count: bucket.count,
      height,
      offsetTop,
      label: formatBucketLabel(bucket.timeBucket),
    });
    offsetTop += height;
  }

  return { segments, totalHeight: offsetTop };
}

/** Binary search for the segment whose [offsetTop, offsetTop+height) contains `offset`. */
function segmentIndexAtOffset(layout: ScrubberLayout, offset: number): number {
  const { segments } = layout;
  if (segments.length === 0) {
    return -1;
  }
  const clamped = Math.min(
    Math.max(0, offset),
    Math.max(0, layout.totalHeight - 1),
  );

  let lo = 0;
  let hi = segments.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if ((segments[mid] as ScrubberSegment).offsetTop <= clamped) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return lo;
}

/** Date label shown while scrubbing, given a scroll offset in px. */
export function offsetToSegment(
  layout: ScrubberLayout,
  scrollOffset: number,
): ScrubberSegment | null {
  const index = segmentIndexAtOffset(layout, scrollOffset);
  return index < 0 ? null : (layout.segments[index] ?? null);
}

/** Scroll offset (px) to jump to the top of a given bucket. */
export function dateToOffset(
  layout: ScrubberLayout,
  timeBucket: string,
): number | null {
  const segment = layout.segments.find((s) => s.timeBucket === timeBucket);
  return segment ? segment.offsetTop : null;
}

/**
 * Map a 0..1 position along the scrubber track to a scroll offset in px.
 * Used when the user clicks/drags the thin track to jump.
 */
export function trackFractionToOffset(
  layout: ScrubberLayout,
  fraction: number,
): number {
  const f = Math.min(1, Math.max(0, fraction));
  return f * layout.totalHeight;
}

/** Map a 0..1 track position to the segment under it (hover preview). */
export function trackFractionToSegment(
  layout: ScrubberLayout,
  fraction: number,
): ScrubberSegment | null {
  return offsetToSegment(layout, trackFractionToOffset(layout, fraction));
}

/**
 * Map the current scroll offset to a 0..1 track position, for placing the
 * scrubber thumb. Returns 0 when the timeline has no height.
 */
export function offsetToTrackFraction(
  layout: ScrubberLayout,
  scrollOffset: number,
): number {
  if (layout.totalHeight <= 0) {
    return 0;
  }
  return Math.min(1, Math.max(0, scrollOffset / layout.totalHeight));
}
