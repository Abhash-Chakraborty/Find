/**
 * Asset-viewer zoom & pan geometry (pure, no React).
 *
 * Models the zoom level and pan offset of a full-screen image viewer, with all
 * clamping centralized so the image can never be zoomed past limits or panned
 * off-screen. Decoupled from rendering and pointer handling so it can be
 * unit-tested; the viewer component drives it from wheel/pointer events.
 *
 * Adapted from the AGPL-3.0 reference project's asset-viewer zoom/pan behavior
 * (Immich). Original © its authors. Part of Find, distributed under AGPL-3.0.
 */

export interface ZoomState {
  /** Current scale; 1 = fit. */
  scale: number;
  /** Pan offset in px from centered, at the current scale. */
  offsetX: number;
  offsetY: number;
}

export interface ViewportSize {
  width: number;
  height: number;
}

export interface ZoomOptions {
  minScale?: number;
  maxScale?: number;
  /** Multiplier applied per zoom-in step (e.g. wheel tick / double-tap). */
  step?: number;
}

const DEFAULT_MIN_SCALE = 1;
const DEFAULT_MAX_SCALE = 5;
const DEFAULT_STEP = 1.5;

export const IDENTITY_ZOOM: ZoomState = { scale: 1, offsetX: 0, offsetY: 0 };

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * Maximum absolute pan offset on each axis: half the overflow of the scaled
 * image beyond the viewport. At scale <= 1 there is no overflow, so 0.
 */
export function maxPanOffset(
  scale: number,
  viewport: ViewportSize,
): { x: number; y: number } {
  const overflowX = Math.max(0, viewport.width * scale - viewport.width);
  const overflowY = Math.max(0, viewport.height * scale - viewport.height);
  return { x: overflowX / 2, y: overflowY / 2 };
}

/** Clamp a zoom state's pan within the pannable bounds for its scale. */
export function clampPan(state: ZoomState, viewport: ViewportSize): ZoomState {
  const max = maxPanOffset(state.scale, viewport);
  return {
    ...state,
    offsetX: clamp(state.offsetX, -max.x, max.x),
    offsetY: clamp(state.offsetY, -max.y, max.y),
  };
}

function resolveOptions(options: ZoomOptions): Required<ZoomOptions> {
  return {
    minScale: options.minScale ?? DEFAULT_MIN_SCALE,
    maxScale: options.maxScale ?? DEFAULT_MAX_SCALE,
    step: options.step ?? DEFAULT_STEP,
  };
}

/**
 * Zoom toward a focal point (e.g. cursor / pinch center) by a multiplicative
 * factor, keeping that point stationary on screen, then clamp scale and pan.
 *
 * `focal` is relative to the viewport center (0,0 = center), in px.
 */
export function zoomBy(
  state: ZoomState,
  factor: number,
  focal: { x: number; y: number },
  viewport: ViewportSize,
  options: ZoomOptions = {},
): ZoomState {
  const { minScale, maxScale } = resolveOptions(options);
  const newScale = clamp(state.scale * factor, minScale, maxScale);
  // Actual factor after clamping (may differ at the limits).
  const applied = newScale / state.scale;

  // Keep the focal point fixed: new_offset = focal - (focal - old_offset) * applied
  const next: ZoomState = {
    scale: newScale,
    offsetX: focal.x - (focal.x - state.offsetX) * applied,
    offsetY: focal.y - (focal.y - state.offsetY) * applied,
  };
  return clampPan(next, viewport);
}

/** One zoom-in step centered on `focal`. */
export function zoomIn(
  state: ZoomState,
  focal: { x: number; y: number },
  viewport: ViewportSize,
  options: ZoomOptions = {},
): ZoomState {
  const { step } = resolveOptions(options);
  return zoomBy(state, step, focal, viewport, options);
}

/** One zoom-out step centered on `focal`. */
export function zoomOut(
  state: ZoomState,
  focal: { x: number; y: number },
  viewport: ViewportSize,
  options: ZoomOptions = {},
): ZoomState {
  const { step } = resolveOptions(options);
  return zoomBy(state, 1 / step, focal, viewport, options);
}

/**
 * Toggle between fit (scale 1) and a zoomed-in scale, used for double-click /
 * double-tap. When already zoomed, returns to identity.
 */
export function toggleZoom(
  state: ZoomState,
  focal: { x: number; y: number },
  viewport: ViewportSize,
  options: ZoomOptions = {},
): ZoomState {
  const { maxScale } = resolveOptions(options);
  if (state.scale > 1.001) {
    return { ...IDENTITY_ZOOM };
  }
  const target = Math.min(maxScale, 2);
  return zoomBy(state, target / state.scale, focal, viewport, options);
}

/** Pan by a delta (px), clamped to bounds. No-op effect at scale <= 1. */
export function panBy(
  state: ZoomState,
  delta: { x: number; y: number },
  viewport: ViewportSize,
): ZoomState {
  return clampPan(
    {
      ...state,
      offsetX: state.offsetX + delta.x,
      offsetY: state.offsetY + delta.y,
    },
    viewport,
  );
}

export function isZoomed(state: ZoomState): boolean {
  return state.scale > 1.001;
}
