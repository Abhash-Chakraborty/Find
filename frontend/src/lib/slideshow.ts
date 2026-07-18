/**
 * Slideshow sequencing (pure, no React/timers).
 *
 * Decides the next index to show given the current position and slideshow
 * settings (loop, shuffle, direction). Timer management and rendering live in
 * the viewer component; this keeps the order logic testable.
 *
 * Adapted from the AGPL-3.0 reference project's slideshow behavior (Immich).
 * Original © its authors. Part of Find, distributed under AGPL-3.0.
 */

export interface SlideshowSettings {
  /** Wrap around to the start (or end) instead of stopping at the boundary. */
  loop?: boolean;
  /** Advance through a shuffled order rather than sequentially. */
  shuffle?: boolean;
  direction?: "forward" | "backward";
}

export interface SlideshowAdvance {
  /** Next index to display, or null when the show should stop. */
  index: number | null;
  /** True when the sequence wrapped past a boundary (loop only). */
  wrapped: boolean;
}

const DEFAULT_INTERVAL_MS = 5000;

/**
 * Compute the next index for a sequential slideshow.
 *
 * Returns `{ index: null }` when at the boundary and `loop` is off — the
 * caller should then stop the show.
 */
export function nextSlideIndex(
  currentIndex: number,
  total: number,
  settings: SlideshowSettings = {},
): SlideshowAdvance {
  if (total <= 0) {
    return { index: null, wrapped: false };
  }
  const step = settings.direction === "backward" ? -1 : 1;
  const raw = currentIndex + step;

  if (raw >= 0 && raw < total) {
    return { index: raw, wrapped: false };
  }
  if (!settings.loop) {
    return { index: null, wrapped: false };
  }
  // Wrap.
  return { index: step > 0 ? 0 : total - 1, wrapped: true };
}

/**
 * Produce a shuffled order of indices [0..total) using a caller-supplied RNG
 * (so tests are deterministic). Fisher–Yates. `rng()` must return [0,1).
 */
export function buildShuffleOrder(total: number, rng: () => number): number[] {
  const order = Array.from({ length: Math.max(0, total) }, (_, i) => i);
  for (let i = order.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    // Both i and j are in-bounds; swap via temp (noUncheckedIndexedAccess).
    const tmp = order[i] as number;
    order[i] = order[j] as number;
    order[j] = tmp;
  }
  return order;
}

/**
 * Advance within a precomputed order (e.g. shuffle order). `position` is the
 * index *into* `order`. Returns the next position and the asset index it maps
 * to, honoring loop.
 */
export function nextInOrder(
  position: number,
  order: number[],
  settings: SlideshowSettings = {},
): { position: number; index: number | null; wrapped: boolean } {
  if (order.length === 0) {
    return { position, index: null, wrapped: false };
  }
  const next = nextSlideIndex(position, order.length, settings);
  if (next.index === null) {
    return { position, index: null, wrapped: false };
  }
  return {
    position: next.index,
    index: order[next.index] ?? null,
    wrapped: next.wrapped,
  };
}

export function normalizeIntervalMs(seconds: number | undefined): number {
  if (
    typeof seconds !== "number" ||
    !Number.isFinite(seconds) ||
    seconds <= 0
  ) {
    return DEFAULT_INTERVAL_MS;
  }
  // Clamp to a sane range: 1s .. 60s.
  return Math.min(60_000, Math.max(1_000, Math.round(seconds * 1000)));
}
