/**
 * Unit tests for the pure viewer zoom/pan geometry.
 *
 * Run with: pnpm vitest run src/__tests__/viewer-zoom.test.ts
 */

import { describe, expect, it } from "vitest";
import {
  clampPan,
  IDENTITY_ZOOM,
  isZoomed,
  maxPanOffset,
  panBy,
  toggleZoom,
  type ZoomState,
  zoomIn,
  zoomOut,
} from "@/lib/viewer-zoom";

const VIEWPORT = { width: 1000, height: 800 };
const CENTER = { x: 0, y: 0 };
const OPTS = { minScale: 1, maxScale: 5, step: 2 };

describe("maxPanOffset", () => {
  it("is zero at or below fit scale", () => {
    expect(maxPanOffset(1, VIEWPORT)).toEqual({ x: 0, y: 0 });
    expect(maxPanOffset(0.5, VIEWPORT)).toEqual({ x: 0, y: 0 });
  });

  it("is half the overflow when zoomed", () => {
    // scale 2 → image 2000x1600, overflow 1000x800, half = 500x400
    expect(maxPanOffset(2, VIEWPORT)).toEqual({ x: 500, y: 400 });
  });
});

describe("zoomIn / zoomOut", () => {
  it("multiplies scale by step, clamped to maxScale", () => {
    let s = zoomIn(IDENTITY_ZOOM, CENTER, VIEWPORT, OPTS);
    expect(s.scale).toBe(2);
    s = zoomIn(s, CENTER, VIEWPORT, OPTS);
    expect(s.scale).toBe(4);
    s = zoomIn(s, CENTER, VIEWPORT, OPTS);
    expect(s.scale).toBe(5); // clamped, not 8
  });

  it("zoomOut divides scale, clamped to minScale", () => {
    const zoomed: ZoomState = { scale: 2, offsetX: 0, offsetY: 0 };
    let s = zoomOut(zoomed, CENTER, VIEWPORT, OPTS);
    expect(s.scale).toBe(1);
    s = zoomOut(s, CENTER, VIEWPORT, OPTS);
    expect(s.scale).toBe(1); // clamped
  });

  it("keeps the focal point stationary when zooming", () => {
    // Zoom toward a focal point 200px right of center.
    const focal = { x: 200, y: 0 };
    const s = zoomIn(IDENTITY_ZOOM, focal, VIEWPORT, OPTS);
    // focal screen position = focal*... ; invariant: focal - (focal-offset)*applied
    // applied factor = 2; offset starts 0 → new offsetX = 200 - 200*2 = -200
    expect(s.offsetX).toBeCloseTo(-200, 6);
  });

  it("clamps pan within bounds after zooming toward an extreme focal", () => {
    const focal = { x: 100000, y: 0 };
    const s = zoomIn(IDENTITY_ZOOM, focal, VIEWPORT, OPTS);
    const max = maxPanOffset(s.scale, VIEWPORT);
    expect(Math.abs(s.offsetX)).toBeLessThanOrEqual(max.x + 1e-6);
  });
});

describe("toggleZoom", () => {
  it("zooms to 2x from fit", () => {
    const s = toggleZoom(IDENTITY_ZOOM, CENTER, VIEWPORT, OPTS);
    expect(s.scale).toBe(2);
  });

  it("returns to fit when already zoomed", () => {
    const zoomed: ZoomState = { scale: 3, offsetX: 100, offsetY: 50 };
    const s = toggleZoom(zoomed, CENTER, VIEWPORT, OPTS);
    expect(s).toEqual(IDENTITY_ZOOM);
  });
});

describe("panBy / clampPan", () => {
  it("has no pannable effect at fit scale", () => {
    const s = panBy(IDENTITY_ZOOM, { x: 300, y: 300 }, VIEWPORT);
    expect(s.offsetX).toBe(0);
    expect(s.offsetY).toBe(0);
  });

  it("pans within bounds when zoomed", () => {
    const zoomed: ZoomState = { scale: 2, offsetX: 0, offsetY: 0 };
    const s = panBy(zoomed, { x: 100, y: -50 }, VIEWPORT);
    expect(s.offsetX).toBe(100);
    expect(s.offsetY).toBe(-50);
  });

  it("clamps pan to the scaled bounds", () => {
    const zoomed: ZoomState = { scale: 2, offsetX: 0, offsetY: 0 };
    const s = panBy(zoomed, { x: 99999, y: 99999 }, VIEWPORT);
    expect(s.offsetX).toBe(500); // maxPanOffset(2).x
    expect(s.offsetY).toBe(400);
  });

  it("clampPan pulls an out-of-bounds state back in", () => {
    const bad: ZoomState = { scale: 2, offsetX: 9999, offsetY: -9999 };
    const s = clampPan(bad, VIEWPORT);
    expect(s.offsetX).toBe(500);
    expect(s.offsetY).toBe(-400);
  });
});

describe("isZoomed", () => {
  it("is false at fit, true when scaled up", () => {
    expect(isZoomed(IDENTITY_ZOOM)).toBe(false);
    expect(isZoomed({ scale: 1.5, offsetX: 0, offsetY: 0 })).toBe(true);
  });
});
