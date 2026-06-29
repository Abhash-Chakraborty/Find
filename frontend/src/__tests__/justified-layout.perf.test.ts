/**
 * Performance smoke test for the justified-layout hot path (Appendix §E).
 *
 * The justified layout runs on every timeline resize/scroll-driven relayout, so
 * it must stay fast even for very large libraries on weak hardware. This test
 * lays out a large item set and asserts the compute stays under budget.
 *
 * Budget is generous (CI machines vary) but catches accidental O(n^2)
 * regressions — the algorithm is single-pass O(n), so 50k items must complete
 * well under the bound.
 *
 * Run with: pnpm vitest run src/__tests__/justified-layout.perf.test.ts
 */

import { describe, expect, it } from "vitest";
import { computeJustifiedLayout } from "@/lib/justified-layout";

// Budget for laying out 50,000 items (one pass). Deliberately loose to avoid
// flakiness across CI hardware while still failing on a quadratic blowup
// (which would take seconds, not tens of ms).
const ITEM_COUNT = 50_000;
const BUDGET_MS = 250;

describe("justified-layout performance", () => {
  it(`lays out ${ITEM_COUNT} items under ${BUDGET_MS}ms`, () => {
    // Varied but deterministic aspect ratios (no Math.random — reproducible).
    const items = Array.from({ length: ITEM_COUNT }, (_, i) => ({
      ratio: 0.5 + (i % 7) * 0.3,
    }));

    const start = performance.now();
    const layout = computeJustifiedLayout(items, {
      containerWidth: 1200,
      targetRowHeight: 235,
      gap: 8,
    });
    const elapsed = performance.now() - start;

    // Correctness sanity: every item placed.
    expect(layout.boxes).toHaveLength(ITEM_COUNT);
    expect(layout.containerHeight).toBeGreaterThan(0);

    // Performance budget.
    expect(elapsed).toBeLessThan(BUDGET_MS);
  });

  it("scales roughly linearly (10x items ≈ 10x time, not 100x)", () => {
    const makeItems = (n: number) =>
      Array.from({ length: n }, (_, i) => ({ ratio: 0.5 + (i % 7) * 0.3 }));
    const opts = { containerWidth: 1200, targetRowHeight: 235, gap: 8 };

    const timeFor = (n: number): number => {
      const items = makeItems(n);
      const start = performance.now();
      computeJustifiedLayout(items, opts);
      return performance.now() - start;
    };

    // Warm up to stabilize JIT before measuring.
    timeFor(5_000);

    const small = Math.max(timeFor(5_000), 0.05); // floor to avoid div-by-tiny
    const large = timeFor(50_000);

    // Linear would be ~10x; allow generous 30x headroom for noise. Quadratic
    // would be ~100x and fail this.
    expect(large / small).toBeLessThan(30);
  });
});
