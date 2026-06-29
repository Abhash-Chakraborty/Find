/**
 * Component tests for the virtualized JustifiedGrid.
 *
 * jsdom has no real layout engine, so we install a fake ResizeObserver that
 * reports a fixed content width. The layout math itself is covered separately
 * in justified-layout.test.ts; here we verify the component wiring: it lays
 * boxes out absolutely, renders an item per box, and exposes the right height.
 *
 * Run with: pnpm vitest run src/__tests__/justified-grid.test.tsx
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { JustifiedGrid } from "@/components/justified-grid";

const CONTAINER_WIDTH = 1000;

class FakeResizeObserver {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    // Immediately report the fixed width so layout can run.
    this.callback(
      [
        {
          target,
          contentRect: { width: CONTAINER_WIDTH, height: 0 } as DOMRectReadOnly,
        } as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  // Keep the whole grid inside the virtualization window for the test.
  vi.stubGlobal("innerHeight", 5000);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

interface Item {
  id: number;
  ratio: number;
}

function renderGrid(items: Item[]) {
  return render(
    <JustifiedGrid
      items={items}
      targetRowHeight={200}
      gap={8}
      getKey={(item) => item.id}
      renderItem={(item) => (
        <div data-testid={`cell-${item.id}`}>photo {item.id}</div>
      )}
    />,
  );
}

describe("JustifiedGrid", () => {
  it("renders one cell per item", () => {
    const items: Item[] = Array.from({ length: 10 }, (_, i) => ({
      id: i,
      ratio: 1.4,
    }));
    renderGrid(items);

    for (const item of items) {
      expect(screen.getByTestId(`cell-${item.id}`)).toBeInTheDocument();
    }
  });

  it("absolutely positions each cell wrapper", () => {
    renderGrid([
      { id: 1, ratio: 1.5 },
      { id: 2, ratio: 0.8 },
    ]);

    const grid = screen.getByTestId("justified-grid");
    const wrappers = within(grid)
      .getAllByTestId(/cell-/)
      .map((el) => el.parentElement as HTMLElement);
    for (const wrapper of wrappers) {
      expect(wrapper.style.position).toBe("absolute");
      // Width should be set to a positive pixel value.
      expect(Number.parseFloat(wrapper.style.width)).toBeGreaterThan(0);
    }
  });

  it("sets a positive container height once measured", () => {
    renderGrid(Array.from({ length: 12 }, (_, i) => ({ id: i, ratio: 1.0 })));
    const grid = screen.getByTestId("justified-grid");
    expect(Number.parseFloat(grid.style.height)).toBeGreaterThan(0);
  });

  it("renders nothing but the container when there are no items", () => {
    renderGrid([]);
    const grid = screen.getByTestId("justified-grid");
    expect(grid).toBeInTheDocument();
    expect(within(grid).queryByTestId(/cell-/)).toBeNull();
  });
});
