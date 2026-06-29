"use client";

/**
 * Full-screen asset viewer with zoom/pan, keyboard navigation, progressive
 * loading, and slideshow mode.
 *
 * All non-trivial logic is delegated to unit-tested pure modules:
 *  - zoom/pan geometry → `@/lib/viewer-zoom`
 *  - progressive load + neighbor preload → `@/lib/viewer-preload`
 *  - slideshow sequencing → `@/lib/slideshow`
 * This component owns DOM wiring (keyboard, pointer, timers, <img> prefetch).
 *
 * Adapted from the AGPL-3.0 reference project's asset-viewer/slideshow UX
 * (Immich). Original © its authors. Part of Find, distributed under AGPL-3.0.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { nextSlideIndex, normalizeIntervalMs } from "@/lib/slideshow";
import {
  buildPreloadPlan,
  displayUrl,
  type ViewerAsset,
} from "@/lib/viewer-preload";
import {
  IDENTITY_ZOOM,
  isZoomed,
  panBy,
  toggleZoom,
  type ZoomState,
  zoomIn,
  zoomOut,
} from "@/lib/viewer-zoom";

interface AssetViewerProps {
  assets: ViewerAsset[];
  index: number;
  onIndexChange: (index: number) => void;
  onClose: () => void;
  /** Slideshow interval in seconds (default 5). */
  slideshowSeconds?: number;
  loopSlideshow?: boolean;
  /** Ids of favorited assets (drives the favorite control's filled state). */
  favoriteIds?: ReadonlySet<number>;
  /** When provided, a favorite toggle is shown; called with the active id. */
  onToggleFavorite?: (id: number) => void;
  /**
   * When provided, an archive control is shown. The asset leaves the list
   * after archiving, so the viewer closes once fired.
   */
  onArchive?: (id: number) => void;
  /**
   * When provided, a move-to-trash control is shown. The asset leaves the list
   * after trashing, so the viewer closes once fired.
   */
  onTrash?: (id: number) => void;
}

export function AssetViewer({
  assets,
  index,
  onIndexChange,
  onClose,
  slideshowSeconds,
  loopSlideshow = true,
  favoriteIds,
  onToggleFavorite,
  onArchive,
  onTrash,
}: AssetViewerProps) {
  const [zoom, setZoom] = useState<ZoomState>(IDENTITY_ZOOM);
  const [originalReady, setOriginalReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [direction, setDirection] = useState<"forward" | "backward">("forward");

  const containerRef = useRef<HTMLDivElement | null>(null);
  const panStateRef = useRef<{ x: number; y: number } | null>(null);

  const active = assets[index];
  const hasPrev = index > 0;
  const hasNext = index < assets.length - 1;

  // Reset zoom + load state whenever the active asset changes.
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset keyed on index
  useEffect(() => {
    setZoom(IDENTITY_ZOOM);
    setOriginalReady(false);
  }, [index]);

  const goTo = useCallback(
    (next: number, dir: "forward" | "backward") => {
      if (next < 0 || next >= assets.length) {
        return;
      }
      setDirection(dir);
      onIndexChange(next);
    },
    [assets.length, onIndexChange],
  );

  const goPrev = useCallback(() => {
    if (hasPrev) {
      goTo(index - 1, "backward");
    }
  }, [goTo, hasPrev, index]);

  const goNext = useCallback(() => {
    if (hasNext) {
      goTo(index + 1, "forward");
    }
  }, [goTo, hasNext, index]);

  const viewport = useCallback(() => {
    const el = containerRef.current;
    return el
      ? { width: el.clientWidth, height: el.clientHeight }
      : { width: 0, height: 0 };
  }, []);

  // --- Progressive load: prefetch active original + neighbors --------------
  const preloadPlan = useMemo(
    () =>
      buildPreloadPlan(assets, index, {
        neighborRadius: 1,
        direction,
        activeOriginalReady: originalReady,
      }),
    [assets, index, direction, originalReady],
  );

  useEffect(() => {
    if (typeof window === "undefined" || preloadPlan.preload.length === 0) {
      return;
    }
    const images: HTMLImageElement[] = [];
    for (const target of preloadPlan.preload) {
      const img = new Image();
      // The active original drives originalReady; neighbors just warm cache.
      if (target.id === active?.id && target.quality === "original") {
        img.onload = () => setOriginalReady(true);
      }
      img.src = target.url;
      images.push(img);
    }
    return () => {
      for (const img of images) {
        img.onload = null;
      }
    };
  }, [preloadPlan, active?.id]);

  // --- Slideshow timer -----------------------------------------------------
  useEffect(() => {
    if (!isPlaying) {
      return;
    }
    const intervalMs = normalizeIntervalMs(slideshowSeconds);
    const timer = setTimeout(() => {
      const advance = nextSlideIndex(index, assets.length, {
        loop: loopSlideshow,
        direction: "forward",
      });
      if (advance.index === null) {
        setIsPlaying(false);
      } else {
        goTo(advance.index, "forward");
      }
    }, intervalMs);
    return () => clearTimeout(timer);
  }, [isPlaying, index, assets.length, slideshowSeconds, loopSlideshow, goTo]);

  // --- Keyboard navigation -------------------------------------------------
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      switch (e.key) {
        case "Escape":
          if (isZoomed(zoom)) {
            setZoom(IDENTITY_ZOOM);
          } else {
            onClose();
          }
          break;
        case "ArrowLeft":
          goPrev();
          break;
        case "ArrowRight":
          goNext();
          break;
        case "+":
        case "=":
          setZoom((z) => zoomIn(z, { x: 0, y: 0 }, viewport()));
          break;
        case "-":
          setZoom((z) => zoomOut(z, { x: 0, y: 0 }, viewport()));
          break;
        case " ":
          e.preventDefault();
          setIsPlaying((p) => !p);
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoom, goPrev, goNext, onClose, viewport]);

  // --- Pointer: drag to pan when zoomed ------------------------------------
  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!isZoomed(zoom)) {
        return;
      }
      e.currentTarget.setPointerCapture?.(e.pointerId);
      panStateRef.current = { x: e.clientX, y: e.clientY };
    },
    [zoom],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const last = panStateRef.current;
      if (!last) {
        return;
      }
      const delta = { x: e.clientX - last.x, y: e.clientY - last.y };
      panStateRef.current = { x: e.clientX, y: e.clientY };
      setZoom((z) => panBy(z, delta, viewport()));
    },
    [viewport],
  );

  const endPan = useCallback(() => {
    panStateRef.current = null;
  }, []);

  const onDoubleClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = containerRef.current?.getBoundingClientRect();
      const focal = rect
        ? {
            x: e.clientX - rect.left - rect.width / 2,
            y: e.clientY - rect.top - rect.height / 2,
          }
        : { x: 0, y: 0 };
      setZoom((z) => toggleZoom(z, focal, viewport()));
    },
    [viewport],
  );

  if (!active) {
    return null;
  }

  const src = displayUrl(active, originalReady);

  return (
    <div
      ref={containerRef}
      data-testid="asset-viewer"
      role="dialog"
      aria-modal="true"
      aria-label={`Image viewer ${index + 1} of ${assets.length}`}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.95)",
        overflow: "hidden",
        touchAction: "none",
        userSelect: "none",
      }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endPan}
      onPointerCancel={endPan}
      onDoubleClick={onDoubleClick}
    >
      {/* biome-ignore lint/a11y/useAltText: decorative full-screen media */}
      <img
        data-testid="viewer-image"
        src={src}
        alt=""
        draggable={false}
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          maxWidth: "100%",
          maxHeight: "100%",
          transform: `translate(-50%, -50%) translate(${zoom.offsetX}px, ${zoom.offsetY}px) scale(${zoom.scale})`,
          transition: panStateRef.current ? "none" : "transform 0.1s ease-out",
          cursor: isZoomed(zoom) ? "grab" : "auto",
        }}
      />

      <button
        type="button"
        aria-label="Close viewer"
        data-testid="viewer-close"
        onClick={onClose}
        style={{ position: "absolute", top: 16, right: 16 }}
      >
        ✕
      </button>

      {onToggleFavorite && (
        <button
          type="button"
          data-testid="viewer-favorite"
          aria-label={
            favoriteIds?.has(active.id) ? "Remove favorite" : "Add favorite"
          }
          aria-pressed={favoriteIds?.has(active.id) ?? false}
          onClick={() => onToggleFavorite(active.id)}
          style={{ position: "absolute", top: 16, left: 16 }}
        >
          {favoriteIds?.has(active.id) ? "♥" : "♡"}
        </button>
      )}

      {onArchive && (
        <button
          type="button"
          data-testid="viewer-archive"
          aria-label="Archive image"
          onClick={() => {
            // The asset leaves the list after archiving — close the viewer.
            onArchive(active.id);
            onClose();
          }}
          style={{ position: "absolute", top: 16, left: 56 }}
        >
          🗄
        </button>
      )}

      {onTrash && (
        <button
          type="button"
          data-testid="viewer-trash"
          aria-label="Move to trash"
          onClick={() => {
            // The asset leaves the list after trashing — close the viewer.
            onTrash(active.id);
            onClose();
          }}
          style={{ position: "absolute", top: 16, left: 96 }}
        >
          🗑
        </button>
      )}

      {hasPrev && (
        <button
          type="button"
          aria-label="Previous image"
          data-testid="viewer-prev"
          onClick={goPrev}
          style={{ position: "absolute", top: "50%", left: 16 }}
        >
          ‹
        </button>
      )}
      {hasNext && (
        <button
          type="button"
          aria-label="Next image"
          data-testid="viewer-next"
          onClick={goNext}
          style={{ position: "absolute", top: "50%", right: 16 }}
        >
          ›
        </button>
      )}

      <button
        type="button"
        aria-label={isPlaying ? "Pause slideshow" : "Play slideshow"}
        data-testid="viewer-slideshow-toggle"
        aria-pressed={isPlaying}
        onClick={() => setIsPlaying((p) => !p)}
        style={{ position: "absolute", bottom: 16, right: 16 }}
      >
        {isPlaying ? "⏸" : "▶"}
      </button>
    </div>
  );
}
