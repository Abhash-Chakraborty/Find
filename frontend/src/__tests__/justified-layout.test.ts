/**
 * Unit tests for the pure justified-layout algorithm.
 *
 * Run with:
 *   pnpm test
 *   pnpm vitest run src/__tests__/justified-layout.test.ts
 */

import { describe, expect, it } from "vitest";
import {
  computeJustifiedLayout,
  type JustifiedInput,
} from "@/lib/justified-layout";

const ratios = (...rs: (number | null)[]): JustifiedInput[] =>
  rs.map((ratio) => ({ ratio }));

describe("computeJustifiedLayout", () => {
  it("returns empty layout for no items", () => {
    const layout = computeJustifiedLayout([], { containerWidth: 1000 });
    expect(layout.rows).toEqual([]);
    expect(layout.boxes).toEqual([]);
    expect(layout.containerHeight).toBe(0);
  });

  it("returns empty layout for zero container width", () => {
    const layout = computeJustifiedLayout(ratios(1, 1, 1), {
      containerWidth: 0,
    });
    expect(layout.boxes).toEqual([]);
    expect(layout.containerHeight).toBe(0);
  });

  it("assigns every item exactly one box, preserving order", () => {
    const layout = computeJustifiedLayout(ratios(1.5, 0.7, 1, 2, 0.5), {
      containerWidth: 1000,
      targetRowHeight: 200,
      gap: 8,
    });
    expect(layout.boxes).toHaveLength(5);
    expect(layout.boxes.map((b) => b.index)).toEqual([0, 1, 2, 3, 4]);
  });

  it("fills the container width exactly on committed (non-last) rows", () => {
    const containerWidth = 1000;
    const gap = 8;
    // Many items so at least one row is committed (not the trailing row).
    const layout = computeJustifiedLayout(
      ratios(...Array.from({ length: 30 }, () => 1.3)),
      { containerWidth, targetRowHeight: 180, gap },
    );

    expect(layout.rows.length).toBeGreaterThan(1);

    // Every row except the last must span the full content width.
    for (const row of layout.rows.slice(0, -1)) {
      const widthsSum = row.boxes.reduce((acc, b) => acc + b.width, 0);
      const gaps = (row.boxes.length - 1) * gap;
      expect(widthsSum + gaps).toBeCloseTo(containerWidth, 4);
    }
  });

  it("gives all boxes in a row the same height", () => {
    const layout = computeJustifiedLayout(
      ratios(...Array.from({ length: 20 }, (_, i) => 0.6 + (i % 5) * 0.3)),
      { containerWidth: 1200, targetRowHeight: 200, gap: 10 },
    );
    for (const row of layout.rows) {
      for (const box of row.boxes) {
        expect(box.height).toBeCloseTo(row.height, 6);
      }
    }
  });

  it("preserves aspect ratio: width equals height * ratio", () => {
    const layout = computeJustifiedLayout(ratios(1.6, 0.75, 1), {
      containerWidth: 900,
      targetRowHeight: 220,
      gap: 8,
    });
    const inputRatios = [1.6, 0.75, 1];
    for (const box of layout.boxes) {
      expect(box.width / box.height).toBeCloseTo(inputRatios[box.index]!, 4);
    }
  });

  it("does not stretch a short trailing row beyond target height", () => {
    const targetRowHeight = 200;
    // Single small item → its own (last) row, must not be blown up to fill width.
    const layout = computeJustifiedLayout(ratios(1), {
      containerWidth: 1000,
      targetRowHeight,
      gap: 8,
    });
    expect(layout.rows).toHaveLength(1);
    expect(layout.rows[0]!.height).toBeLessThanOrEqual(targetRowHeight);
  });

  it("caps a lone very-wide item at maxRowHeightRatio", () => {
    const targetRowHeight = 200;
    const maxRowHeightRatio = 1.5;
    const layout = computeJustifiedLayout(ratios(0.2), {
      containerWidth: 1000,
      targetRowHeight,
      gap: 8,
      maxRowHeightRatio,
    });
    expect(layout.rows[0]!.height).toBeLessThanOrEqual(
      targetRowHeight * maxRowHeightRatio,
    );
  });

  it("treats null/invalid ratios as square (1)", () => {
    const layout = computeJustifiedLayout(ratios(null, 0, -3), {
      containerWidth: 600,
      targetRowHeight: 200,
      gap: 0,
    });
    // All three normalize to 1, so on one full row they share width equally.
    const row = layout.rows[0]!;
    const widths = row.boxes.map((b) => b.width);
    for (const w of widths) {
      expect(w).toBeCloseTo(widths[0]!, 4);
    }
  });

  it("positions rows top-to-bottom with gap spacing", () => {
    const gap = 12;
    const layout = computeJustifiedLayout(
      ratios(...Array.from({ length: 30 }, () => 1.3)),
      { containerWidth: 1000, targetRowHeight: 180, gap },
    );
    for (let i = 1; i < layout.rows.length; i += 1) {
      const prev = layout.rows[i - 1]!;
      const cur = layout.rows[i]!;
      expect(cur.top).toBeCloseTo(prev.top + prev.height + gap, 4);
    }
  });

  it("reports containerHeight matching the last row's extent", () => {
    const layout = computeJustifiedLayout(
      ratios(...Array.from({ length: 12 }, () => 1.0)),
      { containerWidth: 800, targetRowHeight: 160, gap: 8 },
    );
    const lastRow = layout.rows[layout.rows.length - 1]!;
    expect(layout.containerHeight).toBeCloseTo(lastRow.top + lastRow.height, 4);
  });

  it("first box of each row starts at left = 0", () => {
    const layout = computeJustifiedLayout(
      ratios(...Array.from({ length: 25 }, (_, i) => 0.8 + (i % 4) * 0.4)),
      { containerWidth: 1100, targetRowHeight: 190, gap: 8 },
    );
    for (const row of layout.rows) {
      expect(row.boxes[0]!.left).toBe(0);
    }
  });
});
