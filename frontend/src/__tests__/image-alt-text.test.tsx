/**
 * Accessible names for media imagery (#338).
 *
 * Informative tiles must carry a useful name; genuinely decorative duplicates
 * must be absent from the accessibility tree rather than announced with a
 * placeholder label like "Person photo".
 *
 * Run with: pnpm vitest run src/__tests__/image-alt-text.test.tsx
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssetViewer } from "@/components/asset-viewer";
import { TimelineMediaView } from "@/components/timeline-media-view";
import type { ViewerAsset } from "@/lib/viewer-preload";

class FakeResizeObserver {
  constructor(private callback: ResizeObserverCallback) {}

  observe(target: Element) {
    this.callback(
      [
        {
          target,
          contentRect: { width: 1000, height: 0 } as DOMRectReadOnly,
        } as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }

  unobserve() {}
  disconnect() {}
}

class FakeImage {
  onload: (() => void) | null = null;
  set src(_value: string) {}
}

const items = [
  { id: 1, filename: "beach.jpg", createdAt: "2026-03-20T00:00:00Z" },
  { id: 2, filename: "sunset.png", createdAt: "2026-03-19T00:00:00Z" },
];

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("innerHeight", 5000);
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("Image", FakeImage);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderGrid(withAlt: boolean) {
  render(
    <TimelineMediaView
      items={items}
      getId={(item) => item.id}
      getDate={(item) => item.createdAt}
      getThumbnailUrl={(item) => `/thumb/${item.id}`}
      getOriginalUrl={(item) => `/original/${item.id}`}
      getAlt={withAlt ? (item) => item.filename : undefined}
    />,
  );
}

describe("media grid accessible names", () => {
  it("names informative tiles from the filename", () => {
    renderGrid(true);

    expect(screen.getByRole("img", { name: "beach.jpg" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "sunset.png" })).toBeInTheDocument();
  });

  it("falls back to a stable per-asset label when no filename is supplied", () => {
    renderGrid(false);

    expect(screen.getByRole("img", { name: "Photo 1" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Photo 2" })).toBeInTheDocument();
  });

  it("gives every tile a distinct name so they are not interchangeable", () => {
    renderGrid(true);

    const names = screen
      .getAllByRole("img")
      .map((node) => node.getAttribute("alt"));

    expect(names).toHaveLength(new Set(names).size);
    expect(names).not.toContain("");
  });
});

describe("asset viewer accessible name", () => {
  const assets: ViewerAsset[] = [
    {
      id: 7,
      thumbnailUrl: "/thumb/7",
      originalUrl: "/orig/7",
      alt: "beach.jpg",
    },
  ];

  it("prefers the supplied alt text", () => {
    render(
      <AssetViewer
        assets={assets}
        index={0}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("img", { name: "beach.jpg" })).toBeInTheDocument();
  });

  it("falls back to the asset id rather than an empty name", () => {
    render(
      <AssetViewer
        assets={[{ id: 7, thumbnailUrl: "/thumb/7", originalUrl: "/orig/7" }]}
        index={0}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("img", { name: "Photo 7" })).toBeInTheDocument();
  });
});
