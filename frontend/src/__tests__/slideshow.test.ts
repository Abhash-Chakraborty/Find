/**
 * Unit tests for the pure slideshow sequencing.
 *
 * Run with: pnpm vitest run src/__tests__/slideshow.test.ts
 */

import { describe, expect, it } from "vitest";
import {
  buildShuffleOrder,
  nextInOrder,
  nextSlideIndex,
  normalizeIntervalMs,
} from "@/lib/slideshow";

describe("nextSlideIndex", () => {
  it("advances forward by one", () => {
    expect(nextSlideIndex(0, 5)).toEqual({ index: 1, wrapped: false });
    expect(nextSlideIndex(3, 5)).toEqual({ index: 4, wrapped: false });
  });

  it("stops at the end when loop is off", () => {
    expect(nextSlideIndex(4, 5)).toEqual({ index: null, wrapped: false });
  });

  it("wraps to start at the end when loop is on", () => {
    expect(nextSlideIndex(4, 5, { loop: true })).toEqual({
      index: 0,
      wrapped: true,
    });
  });

  it("goes backward when direction is backward", () => {
    expect(nextSlideIndex(3, 5, { direction: "backward" })).toEqual({
      index: 2,
      wrapped: false,
    });
  });

  it("stops at the start going backward without loop", () => {
    expect(nextSlideIndex(0, 5, { direction: "backward" })).toEqual({
      index: null,
      wrapped: false,
    });
  });

  it("wraps to the end going backward with loop", () => {
    expect(nextSlideIndex(0, 5, { direction: "backward", loop: true })).toEqual(
      { index: 4, wrapped: true },
    );
  });

  it("returns null for an empty set", () => {
    expect(nextSlideIndex(0, 0)).toEqual({ index: null, wrapped: false });
  });
});

describe("buildShuffleOrder", () => {
  it("is a permutation of [0..total)", () => {
    const order = buildShuffleOrder(6, makeSeqRng());
    expect([...order].sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5]);
  });

  it("is deterministic for a given rng", () => {
    const a = buildShuffleOrder(8, makeSeqRng());
    const b = buildShuffleOrder(8, makeSeqRng());
    expect(a).toEqual(b);
  });

  it("handles empty and single-element sets", () => {
    expect(buildShuffleOrder(0, makeSeqRng())).toEqual([]);
    expect(buildShuffleOrder(1, makeSeqRng())).toEqual([0]);
  });
});

describe("nextInOrder", () => {
  const order = [2, 0, 3, 1]; // a shuffle order

  it("advances position and maps to the asset index", () => {
    expect(nextInOrder(0, order)).toEqual({
      position: 1,
      index: 0,
      wrapped: false,
    });
    expect(nextInOrder(2, order)).toEqual({
      position: 3,
      index: 1,
      wrapped: false,
    });
  });

  it("stops at the end of the order without loop", () => {
    expect(nextInOrder(3, order)).toEqual({
      position: 3,
      index: null,
      wrapped: false,
    });
  });

  it("wraps within the order with loop", () => {
    expect(nextInOrder(3, order, { loop: true })).toEqual({
      position: 0,
      index: 2,
      wrapped: true,
    });
  });

  it("returns null for an empty order", () => {
    expect(nextInOrder(0, [])).toEqual({
      position: 0,
      index: null,
      wrapped: false,
    });
  });
});

describe("normalizeIntervalMs", () => {
  it("converts seconds to ms", () => {
    expect(normalizeIntervalMs(5)).toBe(5000);
  });

  it("falls back to default for invalid input", () => {
    expect(normalizeIntervalMs(undefined)).toBe(5000);
    expect(normalizeIntervalMs(0)).toBe(5000);
    expect(normalizeIntervalMs(-3)).toBe(5000);
    expect(normalizeIntervalMs(Number.NaN)).toBe(5000);
  });

  it("clamps to the 1s..60s range", () => {
    expect(normalizeIntervalMs(0.1)).toBe(1000);
    expect(normalizeIntervalMs(120)).toBe(60000);
  });
});

/** Deterministic RNG cycling through a fixed low-discrepancy sequence. */
function makeSeqRng(): () => number {
  const seq = [0.1, 0.7, 0.3, 0.9, 0.5, 0.2, 0.8, 0.4];
  let i = 0;
  return () => seq[i++ % seq.length]!;
}
