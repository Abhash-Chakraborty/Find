/**
 * Unit tests for the pure viewer progressive-load / preload selection.
 *
 * Run with: pnpm vitest run src/__tests__/viewer-preload.test.ts
 */

import { describe, expect, it } from "vitest";
import {
  buildPreloadPlan,
  displayUrl,
  type ViewerAsset,
} from "@/lib/viewer-preload";

const asset = (id: number, withOriginal = true): ViewerAsset => ({
  id,
  thumbnailUrl: `/thumb/${id}`,
  originalUrl: withOriginal ? `/orig/${id}` : null,
});

const assets = (n: number, withOriginal = true): ViewerAsset[] =>
  Array.from({ length: n }, (_, i) => asset(i, withOriginal));

describe("buildPreloadPlan", () => {
  it("returns empty plan for out-of-range index", () => {
    expect(buildPreloadPlan(assets(3), -1).preload).toEqual([]);
    expect(buildPreloadPlan(assets(3), 5).preload).toEqual([]);
  });

  it("leads with the active asset's original when not yet shown", () => {
    const plan = buildPreloadPlan(assets(5), 2, {
      activeOriginalReady: false,
      neighborRadius: 0,
    });
    expect(plan.preload[0]).toEqual({
      id: 2,
      url: "/orig/2",
      quality: "original",
    });
    expect(plan.activeQuality).toBe("thumbnail");
  });

  it("does not re-queue the active original once it is ready", () => {
    const plan = buildPreloadPlan(assets(5), 2, {
      activeOriginalReady: true,
      neighborRadius: 0,
    });
    expect(plan.preload).toEqual([]);
    expect(plan.activeQuality).toBe("original");
  });

  it("preloads neighbors forward-first by default", () => {
    const plan = buildPreloadPlan(assets(5), 2, {
      activeOriginalReady: true,
      neighborRadius: 1,
    });
    expect(plan.preload.map((p) => p.id)).toEqual([3, 1]);
  });

  it("biases preload order backward when navigating backward", () => {
    const plan = buildPreloadPlan(assets(5), 2, {
      activeOriginalReady: true,
      neighborRadius: 1,
      direction: "backward",
    });
    expect(plan.preload.map((p) => p.id)).toEqual([1, 3]);
  });

  it("orders multi-radius neighbors nearest-first", () => {
    const plan = buildPreloadPlan(assets(7), 3, {
      activeOriginalReady: true,
      neighborRadius: 2,
      direction: "forward",
    });
    // 1,-1,2,-2 around index 3 → 4,2,5,1
    expect(plan.preload.map((p) => p.id)).toEqual([4, 2, 5, 1]);
  });

  it("skips neighbors past the array bounds", () => {
    const plan = buildPreloadPlan(assets(3), 0, {
      activeOriginalReady: true,
      neighborRadius: 2,
      direction: "forward",
    });
    // around index 0: 1,(-1 oob),2,(-2 oob) → 1,2
    expect(plan.preload.map((p) => p.id)).toEqual([1, 2]);
  });

  it("falls back to thumbnail quality when a neighbor has no original", () => {
    const mixed = [asset(0), asset(1, false), asset(2)];
    const plan = buildPreloadPlan(mixed, 0, {
      activeOriginalReady: true,
      neighborRadius: 1,
    });
    const neighbor = plan.preload.find((p) => p.id === 1);
    expect(neighbor).toEqual({ id: 1, url: "/thumb/1", quality: "thumbnail" });
  });

  it("active asset without original shows thumbnail and queues nothing for it", () => {
    const plan = buildPreloadPlan([asset(0, false)], 0, {
      activeOriginalReady: false,
      neighborRadius: 0,
    });
    expect(plan.activeQuality).toBe("thumbnail");
    expect(plan.preload).toEqual([]);
  });
});

describe("displayUrl", () => {
  it("shows original once ready", () => {
    expect(displayUrl(asset(1), true)).toBe("/orig/1");
  });

  it("shows thumbnail until original is ready", () => {
    expect(displayUrl(asset(1), false)).toBe("/thumb/1");
  });

  it("shows thumbnail when there is no original even if 'ready'", () => {
    expect(displayUrl(asset(1, false), true)).toBe("/thumb/1");
  });
});
