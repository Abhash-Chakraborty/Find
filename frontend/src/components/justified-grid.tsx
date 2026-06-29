"use client";

/**
 * Virtualized justified photo grid.
 *
 * Computes a justified layout (variable row heights from real aspect ratios)
 * and renders only the boxes within the current scroll viewport, so very large
 * libraries stay smooth on weak hardware. Layout math lives in
 * `@/lib/justified-layout` and is unit-tested separately; this component owns
 * measurement, virtualization, and rendering only.
 */

import {
  type ReactNode,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  computeJustifiedLayout,
  type JustifiedBox,
} from "@/lib/justified-layout";

export interface JustifiedGridItem {
  ratio: number | null | undefined;
}

interface JustifiedGridProps<T extends JustifiedGridItem> {
  items: T[];
  /** Desired row height before per-row scaling. */
  targetRowHeight?: number;
  gap?: number;
  /** Extra vertical px rendered above/below the viewport to avoid blank flashes. */
  overscanPx?: number;
  className?: string;
  getKey: (item: T, index: number) => string | number;
  renderItem: (item: T, index: number, box: JustifiedBox) => ReactNode;
}

const DEFAULT_TARGET_ROW_HEIGHT = 235;
const DEFAULT_GAP = 8;
const DEFAULT_OVERSCAN_PX = 600;

// Use layout effect in the browser, plain effect during SSR to avoid warnings.
const useIsomorphicLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

export function JustifiedGrid<T extends JustifiedGridItem>({
  items,
  targetRowHeight = DEFAULT_TARGET_ROW_HEIGHT,
  gap = DEFAULT_GAP,
  overscanPx = DEFAULT_OVERSCAN_PX,
  className,
  getKey,
  renderItem,
}: JustifiedGridProps<T>) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  // Measure container width (content box) and react to resizes.
  useIsomorphicLayoutEffect(() => {
    const element = containerRef.current;
    if (!element || typeof ResizeObserver === "undefined") {
      if (element) {
        setContainerWidth(element.clientWidth);
      }
      return;
    }
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    // Seed with the current width first, then let the observer take over so a
    // synchronous observe() callback isn't immediately overwritten by a 0.
    setContainerWidth(element.clientWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Track the scroll position of the nearest scrolling ancestor (or window),
  // expressed relative to the grid's own top, plus the viewport height.
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const update = () => {
      const element = containerRef.current;
      if (!element) {
        return;
      }
      const rect = element.getBoundingClientRect();
      // How far the grid's top has scrolled above the viewport top.
      setScrollTop(Math.max(0, -rect.top));
      setViewportHeight(window.innerHeight || 0);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  const layout = useMemo(
    () =>
      computeJustifiedLayout(items, {
        containerWidth,
        targetRowHeight,
        gap,
      }),
    [items, containerWidth, targetRowHeight, gap],
  );

  // Virtualization: keep rows whose vertical span intersects the overscanned
  // viewport. Falls back to all rows when viewport height is unknown (SSR).
  const visible = useMemo(() => {
    if (viewportHeight === 0) {
      return layout.boxes.map((box) => ({
        box,
        item: items[box.index] as T,
      }));
    }
    const top = scrollTop - overscanPx;
    const bottom = scrollTop + viewportHeight + overscanPx;
    const result: { box: JustifiedBox; item: T }[] = [];
    for (const row of layout.rows) {
      const rowBottom = row.top + row.height;
      if (rowBottom < top || row.top > bottom) {
        continue;
      }
      for (const box of row.boxes) {
        // box.index always references a valid item (boxes are derived from items).
        result.push({ box, item: items[box.index] as T });
      }
    }
    return result;
  }, [layout, items, scrollTop, viewportHeight, overscanPx]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        position: "relative",
        width: "100%",
        height: layout.containerHeight,
      }}
      data-testid="justified-grid"
    >
      {visible.map(({ box, item }) => (
        <div
          key={getKey(item, box.index)}
          style={{
            position: "absolute",
            top: box.top,
            left: box.left,
            width: box.width,
            height: box.height,
          }}
        >
          {renderItem(item, box.index, box)}
        </div>
      ))}
    </div>
  );
}
