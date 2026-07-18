/**
 * Justified grid layout (pure geometry, no React).
 *
 * Given each item's aspect ratio, packs items into rows so every row fills the
 * container width at roughly `targetRowHeight`, scaling each row's height to
 * make its items fit exactly — the layout used by photo timelines. Decoupled
 * from rendering so it can be unit-tested and reused by the virtualizer.
 *
 * Adapted from the AGPL-3.0 reference project's justified-layout behavior
 * (Immich). Original © its authors. This file is part of Find and is
 * distributed under AGPL-3.0. See NOTICE.
 */

export interface JustifiedInput {
  /** Aspect ratio (width / height). Falls back to 1 when missing/invalid. */
  ratio: number | null | undefined;
}

export interface JustifiedBox {
  /** Index into the original input array. */
  index: number;
  top: number;
  left: number;
  width: number;
  height: number;
}

export interface JustifiedRow {
  top: number;
  height: number;
  boxes: JustifiedBox[];
}

export interface JustifiedLayout {
  rows: JustifiedRow[];
  boxes: JustifiedBox[];
  /** Total content height including gaps. */
  containerHeight: number;
}

export interface JustifiedOptions {
  /** Available content width in px (excludes the container's own padding). */
  containerWidth: number;
  /** Desired row height before per-row scaling. */
  targetRowHeight?: number;
  /** Gap between items and between rows, in px. */
  gap?: number;
  /**
   * A row is allowed to exceed `targetRowHeight` by at most this factor before
   * it is force-broken. Prevents a lone wide panorama from creating a huge row.
   */
  maxRowHeightRatio?: number;
}

const DEFAULT_TARGET_ROW_HEIGHT = 235;
const DEFAULT_GAP = 8;
const DEFAULT_MAX_ROW_HEIGHT_RATIO = 1.5;
const MIN_RATIO = 0.1;
const MAX_RATIO = 10;

function normalizeRatio(ratio: number | null | undefined): number {
  if (typeof ratio !== "number" || !Number.isFinite(ratio) || ratio <= 0) {
    return 1;
  }
  // Clamp pathological ratios so one bad value can't blow up a row.
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio));
}

/**
 * Compute a justified layout for the given items.
 *
 * The algorithm is single-pass and greedy: accumulate items into the current
 * row until adding another would push the scaled row height below the target,
 * then commit the row at the height that makes its items exactly fill the
 * width. The final (possibly short) row is left at target height rather than
 * stretched, matching common photo-grid behavior.
 */
export function computeJustifiedLayout(
  items: JustifiedInput[],
  options: JustifiedOptions,
): JustifiedLayout {
  const targetRowHeight = options.targetRowHeight ?? DEFAULT_TARGET_ROW_HEIGHT;
  const gap = options.gap ?? DEFAULT_GAP;
  const maxRowHeightRatio =
    options.maxRowHeightRatio ?? DEFAULT_MAX_ROW_HEIGHT_RATIO;
  const containerWidth = Math.max(0, options.containerWidth);

  const rows: JustifiedRow[] = [];
  const allBoxes: JustifiedBox[] = [];

  if (containerWidth === 0 || items.length === 0) {
    return { rows, boxes: allBoxes, containerHeight: 0 };
  }

  const ratios = items.map((item) => normalizeRatio(item.ratio));
  let top = 0;

  let rowStart = 0;
  while (rowStart < items.length) {
    // Grow the row until the scaled height would drop below target, or until a
    // single very-wide item already overflows the width on its own.
    let rowEnd = rowStart;
    let summedRatio = 0;

    while (rowEnd < items.length) {
      const nextSummedRatio = summedRatio + (ratios[rowEnd] ?? 1);
      const gapsWidth = (rowEnd - rowStart) * gap;
      const available = containerWidth - gapsWidth;
      // Height if this row (rowStart..rowEnd inclusive) filled the width.
      const scaledHeight = available / nextSummedRatio;

      summedRatio = nextSummedRatio;
      rowEnd += 1;

      if (scaledHeight <= targetRowHeight) {
        // Adding this item brought us at/below target — close the row here.
        break;
      }
    }

    const count = rowEnd - rowStart;
    const gapsWidth = (count - 1) * gap;
    const available = containerWidth - gapsWidth;
    let rowHeight = available / summedRatio;

    const isLastRow = rowEnd >= items.length;
    // A short trailing row shouldn't be stretched tall; cap it at target.
    if (isLastRow && rowHeight > targetRowHeight) {
      rowHeight = targetRowHeight;
    }
    // Guard against a lone wide item producing an enormous row.
    const maxHeight = targetRowHeight * maxRowHeightRatio;
    if (rowHeight > maxHeight) {
      rowHeight = maxHeight;
    }

    const boxes: JustifiedBox[] = [];
    let left = 0;
    for (let i = rowStart; i < rowEnd; i += 1) {
      const width = rowHeight * (ratios[i] ?? 1);
      const box: JustifiedBox = {
        index: i,
        top,
        left,
        width,
        height: rowHeight,
      };
      boxes.push(box);
      allBoxes.push(box);
      left += width + gap;
    }

    rows.push({ top, height: rowHeight, boxes });
    top += rowHeight + gap;
    rowStart = rowEnd;
  }

  // containerHeight excludes the trailing gap after the last row.
  const containerHeight = top > 0 ? top - gap : 0;
  return { rows, boxes: allBoxes, containerHeight };
}
