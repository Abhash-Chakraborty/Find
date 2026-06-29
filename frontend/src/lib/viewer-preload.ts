/**
 * Asset-viewer progressive loading & neighbor preloading (pure, no React).
 *
 * Find exposes two resolutions per asset: a thumbnail and the original. The
 * viewer shows the thumbnail instantly (it's usually already cached from the
 * grid), then loads the original on demand — immediately for the active asset,
 * and lazily for neighbors so left/right navigation feels instant. This module
 * decides *which* asset URLs to preload given the current index and direction;
 * the component owns the actual <img> / Image() prefetching.
 *
 * Adapted from the AGPL-3.0 reference project's asset-viewer loading discipline
 * (Immich). Original © its authors. Part of Find, distributed under AGPL-3.0.
 */

export type LoadQuality = "thumbnail" | "original";

export interface ViewerAsset {
  id: number;
  thumbnailUrl: string;
  /** Original/full-res URL; may be null until resolved. */
  originalUrl?: string | null;
}

export interface PreloadTarget {
  id: number;
  url: string;
  quality: LoadQuality;
}

export interface PreloadPlan {
  /** Quality to display for the active asset right now. */
  activeQuality: LoadQuality;
  /** Assets to prefetch in the background, nearest-first. */
  preload: PreloadTarget[];
}

export interface PreloadOptions {
  /** How many neighbors on each side to preload. */
  neighborRadius?: number;
  /** Bias preload order toward this direction. */
  direction?: "forward" | "backward" | "none";
  /**
   * Whether the active original has loaded yet. While false the viewer shows
   * the thumbnail; once true it shows the original. Drives activeQuality.
   */
  activeOriginalReady?: boolean;
}

const DEFAULT_NEIGHBOR_RADIUS = 1;

function originalOrThumb(asset: ViewerAsset): PreloadTarget {
  return asset.originalUrl
    ? { id: asset.id, url: asset.originalUrl, quality: "original" }
    : { id: asset.id, url: asset.thumbnailUrl, quality: "thumbnail" };
}

/**
 * Build the ordered preload plan for the asset at `index`.
 *
 * Order: the active asset's original first (so it replaces the thumbnail asap),
 * then neighbors outward, biased by `direction` (the side the user is heading
 * toward is preloaded before the side they came from), each at original quality
 * when a URL is known, else thumbnail.
 */
export function buildPreloadPlan(
  assets: ViewerAsset[],
  index: number,
  options: PreloadOptions = {},
): PreloadPlan {
  const radius = options.neighborRadius ?? DEFAULT_NEIGHBOR_RADIUS;
  const direction = options.direction ?? "none";
  const activeOriginalReady = options.activeOriginalReady ?? false;

  if (index < 0 || index >= assets.length) {
    return { activeQuality: "thumbnail", preload: [] };
  }

  // index is bounds-checked above, so this is always defined.
  const active = assets[index] as ViewerAsset;
  const preload: PreloadTarget[] = [];

  // Active asset's original leads the queue (unless it's already shown).
  if (active.originalUrl && !activeOriginalReady) {
    preload.push({
      id: active.id,
      url: active.originalUrl,
      quality: "original",
    });
  }

  // Collect neighbor offsets nearest-first: 1, -1, 2, -2, ... then bias.
  const offsets: number[] = [];
  for (let d = 1; d <= radius; d += 1) {
    const forward = d;
    const backward = -d;
    if (direction === "backward") {
      offsets.push(backward, forward);
    } else {
      // forward or none → forward side first
      offsets.push(forward, backward);
    }
  }

  for (const offset of offsets) {
    const neighborIndex = index + offset;
    if (neighborIndex < 0 || neighborIndex >= assets.length) {
      continue;
    }
    // neighborIndex is bounds-checked above.
    preload.push(originalOrThumb(assets[neighborIndex] as ViewerAsset));
  }

  return {
    activeQuality:
      activeOriginalReady && active.originalUrl ? "original" : "thumbnail",
    preload,
  };
}

/** Resolve which URL the viewer should display for the active asset now. */
export function displayUrl(
  asset: ViewerAsset,
  activeOriginalReady: boolean,
): string {
  if (activeOriginalReady && asset.originalUrl) {
    return asset.originalUrl;
  }
  return asset.thumbnailUrl;
}
