/**
 * Pure helpers for route-agnostic media timelines.
 *
 * The grouping and scroll-mapping behavior is adapted from the AGPL-3.0
 * reference project's month timeline. Original copyright belongs to its
 * authors. This file is part of Find and is distributed under AGPL-3.0.
 * See NOTICE.
 */

import type { ScrubberLayout, ScrubberSegment } from "@/lib/timeline-scrubber";

export type MediaTimelineOrder = "newest" | "oldest";

export interface MediaTimelineGroup<T> {
  /** `YYYY-MM-01` for dated media, or `undated` when no valid date exists. */
  timeBucket: string;
  label: string;
  items: T[];
}

export interface TimelineSectionMeasurement {
  timeBucket: string;
  /** Section top relative to the timeline root, in real rendered pixels. */
  top: number;
  /** Section height in real rendered pixels. */
  height: number;
}

const MONTH_FORMATTER = new Intl.DateTimeFormat("en", {
  month: "long",
  timeZone: "UTC",
  year: "numeric",
});

function validDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function mediaMonthBucket(
  value: string | null | undefined,
): string | null {
  const date = validDate(value);
  if (!date) {
    return null;
  }

  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  return `${year}-${month}-01`;
}

export function mediaMonthLabel(timeBucket: string): string {
  if (timeBucket === "undated") {
    return "Undated";
  }

  const match = /^(\d{4})-(\d{2})-01$/.exec(timeBucket);
  if (!match) {
    return timeBucket;
  }

  const year = Number.parseInt(match[1] ?? "", 10);
  const month = Number.parseInt(match[2] ?? "", 10);
  if (!Number.isFinite(year) || month < 1 || month > 12) {
    return timeBucket;
  }

  return MONTH_FORMATTER.format(new Date(Date.UTC(year, month - 1, 1)));
}

/**
 * Group arbitrary route media by month and sort both groups and assets by date.
 * Invalid or missing dates are retained in a final `Undated` section.
 */
export function groupMediaByMonth<T>(
  items: readonly T[],
  getDate: (item: T) => string | null | undefined,
  order: MediaTimelineOrder = "newest",
): MediaTimelineGroup<T>[] {
  const dated = new Map<string, Array<{ item: T; timestamp: number }>>();
  const undated: T[] = [];

  for (const item of items) {
    const value = getDate(item);
    const date = validDate(value);
    const timeBucket = mediaMonthBucket(value);
    if (!date || !timeBucket) {
      undated.push(item);
      continue;
    }

    const group = dated.get(timeBucket) ?? [];
    group.push({ item, timestamp: date.getTime() });
    dated.set(timeBucket, group);
  }

  const direction = order === "newest" ? -1 : 1;
  const groups = [...dated.entries()]
    .sort(([left], [right]) => left.localeCompare(right) * direction)
    .map(([timeBucket, group]) => ({
      timeBucket,
      label: mediaMonthLabel(timeBucket),
      items: group
        .sort((left, right) => (left.timestamp - right.timestamp) * direction)
        .map(({ item }) => item),
    }));

  if (undated.length > 0) {
    groups.push({ timeBucket: "undated", label: "Undated", items: undated });
  }

  return groups;
}

export function timelineBucketsFromGroups<T>(
  groups: readonly MediaTimelineGroup<T>[],
): Array<{ timeBucket: string; count: number }> {
  return groups.map((group) => ({
    timeBucket: group.timeBucket,
    count: group.items.length,
  }));
}

export function mediaAspectRatio(
  width: number | null | undefined,
  height: number | null | undefined,
): number {
  if (
    typeof width !== "number" ||
    typeof height !== "number" ||
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  ) {
    return 1;
  }

  return width / height;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function segmentForBucket(
  layout: ScrubberLayout,
  timeBucket: string,
): ScrubberSegment | undefined {
  return layout.segments.find((segment) => segment.timeBucket === timeBucket);
}

/**
 * Translate real DOM scroll pixels into the scrubber's estimated-height space.
 * Preserving within-section progress keeps the thumb synchronized even though
 * justified rows make each rendered month a different height than its estimate.
 */
export function actualOffsetToScrubberOffset(
  measurements: readonly TimelineSectionMeasurement[],
  layout: ScrubberLayout,
  actualOffset: number,
): number {
  if (measurements.length === 0 || layout.segments.length === 0) {
    return 0;
  }

  const ordered = [...measurements].sort((left, right) => left.top - right.top);
  const clampedOffset = Math.max(0, actualOffset);
  let active = ordered[0];

  for (const measurement of ordered) {
    if (measurement.top > clampedOffset) {
      break;
    }
    active = measurement;
  }

  if (!active) {
    return 0;
  }

  const segment = segmentForBucket(layout, active.timeBucket);
  if (!segment) {
    return 0;
  }

  const progress =
    active.height > 0
      ? clamp((clampedOffset - active.top) / active.height, 0, 1)
      : 0;
  return segment.offsetTop + progress * segment.height;
}

/** Reverse `actualOffsetToScrubberOffset` for a scrubber-driven window jump. */
export function scrubberOffsetToActualOffset(
  measurements: readonly TimelineSectionMeasurement[],
  layout: ScrubberLayout,
  scrubberOffset: number,
): number {
  if (measurements.length === 0 || layout.segments.length === 0) {
    return 0;
  }

  const clampedOffset = clamp(scrubberOffset, 0, layout.totalHeight);
  let segment = layout.segments[0];
  for (const candidate of layout.segments) {
    if (candidate.offsetTop > clampedOffset) {
      break;
    }
    segment = candidate;
  }

  if (!segment) {
    return 0;
  }

  const measurement = measurements.find(
    (candidate) => candidate.timeBucket === segment.timeBucket,
  );
  if (!measurement) {
    return 0;
  }

  const progress =
    segment.height > 0
      ? clamp((clampedOffset - segment.offsetTop) / segment.height, 0, 1)
      : 0;
  return measurement.top + progress * measurement.height;
}
