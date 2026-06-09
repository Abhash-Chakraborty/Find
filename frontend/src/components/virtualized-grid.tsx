"use client";

import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type VirtualizedGridProps<T> = {
  items: T[];
  className: string;
  estimateRowHeight: number;
  gap?: number;
  overscanRows?: number;
  getKey: (item: T, index: number) => string | number;
  renderItem: (item: T, index: number) => ReactNode;
};

type VirtualWindow = {
  columns: number;
  startRow: number;
  endRow: number;
};

const DEFAULT_OVERSCAN_ROWS = 4;

function getColumnCount(element: HTMLElement | null) {
  if (!element || typeof window === "undefined") {
    return 1;
  }

  const columns = window.getComputedStyle(element).gridTemplateColumns;
  if (!columns || columns === "none") {
    return 1;
  }

  return Math.max(1, columns.split(" ").filter(Boolean).length);
}

function getScrollParents(element: HTMLElement | null) {
  if (!element || typeof window === "undefined") {
    return [];
  }

  const parents: HTMLElement[] = [];
  let parent = element.parentElement;

  while (parent && parent !== document.body) {
    const style = window.getComputedStyle(parent);
    const overflow = `${style.overflow}${style.overflowY}${style.overflowX}`;
    if (/(auto|scroll|overlay)/.test(overflow)) {
      parents.push(parent);
    }
    parent = parent.parentElement;
  }

  return parents;
}

export function VirtualizedGrid<T>({
  items,
  className,
  estimateRowHeight,
  gap = 16,
  overscanRows = DEFAULT_OVERSCAN_ROWS,
  getKey,
  renderItem,
}: VirtualizedGridProps<T>) {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const [virtualWindow, setVirtualWindow] = useState<VirtualWindow>({
    columns: 1,
    startRow: 0,
    endRow: DEFAULT_OVERSCAN_ROWS + 4,
  });

  const rowStride = estimateRowHeight + gap;

  const updateVirtualWindow = useCallback(() => {
    if (typeof window === "undefined") {
      return;
    }

    const element = gridRef.current;
    const columns = getColumnCount(element);

    if (!element) {
      setVirtualWindow({
        columns,
        startRow: 0,
        endRow: Math.ceil(items.length / columns),
      });
      return;
    }

    const rect = element.getBoundingClientRect();
    const viewportHeight = window.innerHeight || 800;
    const beforeViewport = Math.max(0, -rect.top);
    const firstVisibleRow = Math.floor(beforeViewport / rowStride);
    const visibleRows = Math.ceil(viewportHeight / rowStride);
    const totalRows = Math.ceil(items.length / columns);
    const startRow = Math.max(0, firstVisibleRow - overscanRows);
    const endRow = Math.min(
      totalRows,
      firstVisibleRow + visibleRows + overscanRows,
    );

    setVirtualWindow((current) => {
      if (
        current.columns === columns &&
        current.startRow === startRow &&
        current.endRow === endRow
      ) {
        return current;
      }

      return { columns, startRow, endRow };
    });
  }, [items.length, overscanRows, rowStride]);

  useEffect(() => {
    updateVirtualWindow();

    window.addEventListener("scroll", updateVirtualWindow, { passive: true });
    window.addEventListener("resize", updateVirtualWindow);

    const scrollParents = getScrollParents(gridRef.current);
    for (const scrollParent of scrollParents) {
      scrollParent.addEventListener("scroll", updateVirtualWindow, {
        passive: true,
      });
    }

    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(updateVirtualWindow);

    if (gridRef.current) {
      observer?.observe(gridRef.current);
    }

    return () => {
      window.removeEventListener("scroll", updateVirtualWindow);
      window.removeEventListener("resize", updateVirtualWindow);
      for (const scrollParent of scrollParents) {
        scrollParent.removeEventListener("scroll", updateVirtualWindow);
      }
      observer?.disconnect();
    };
  }, [updateVirtualWindow]);

  const { visibleItems, topSpacerHeight, bottomSpacerHeight } = useMemo(() => {
    const columns = Math.max(1, virtualWindow.columns);
    const totalRows = Math.ceil(items.length / columns);
    const startRow = Math.min(virtualWindow.startRow, totalRows);
    const endRow = Math.min(virtualWindow.endRow, totalRows);
    const startIndex = startRow * columns;
    const endIndex = Math.min(items.length, endRow * columns);

    return {
      visibleItems: items
        .slice(startIndex, endIndex)
        .map((item, index) => ({ item, index: startIndex + index })),
      topSpacerHeight: startRow > 0 ? startRow * rowStride : 0,
      bottomSpacerHeight:
        endRow < totalRows ? Math.max(0, (totalRows - endRow) * rowStride) : 0,
    };
  }, [items, rowStride, virtualWindow]);

  return (
    <div ref={gridRef} className={className}>
      {topSpacerHeight > 0 && (
        <div
          aria-hidden="true"
          style={{ height: topSpacerHeight, gridColumn: "1 / -1" }}
        />
      )}
      {visibleItems.map(({ item, index }) => (
        <div key={getKey(item, index)} style={{ display: "contents" }}>
          {renderItem(item, index)}
        </div>
      ))}
      {bottomSpacerHeight > 0 && (
        <div
          aria-hidden="true"
          style={{ height: bottomSpacerHeight, gridColumn: "1 / -1" }}
        />
      )}
    </div>
  );
}
