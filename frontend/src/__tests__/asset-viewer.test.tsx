/**
 * Component tests for the AssetViewer.
 *
 * The heavy logic (zoom/pan, preload, slideshow) is covered by the pure-module
 * tests; here we verify wiring: it renders the active asset, navigates via
 * buttons + arrow keys, closes on Escape, swaps thumbnail→original once the
 * preloaded original "loads", and toggles slideshow.
 *
 * Run with: pnpm vitest run src/__tests__/asset-viewer.test.tsx
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssetViewer } from "@/components/asset-viewer";
import type { ViewerAsset } from "@/lib/viewer-preload";

const ASSETS: ViewerAsset[] = [
  { id: 0, thumbnailUrl: "/thumb/0", originalUrl: "/orig/0" },
  { id: 1, thumbnailUrl: "/thumb/1", originalUrl: "/orig/1" },
  { id: 2, thumbnailUrl: "/thumb/2", originalUrl: "/orig/2" },
];

// Capture created Image() instances so we can fire their onload.
let createdImages: FakeImage[] = [];

class FakeImage {
  onload: (() => void) | null = null;
  private _src = "";
  constructor() {
    createdImages.push(this);
  }
  set src(value: string) {
    this._src = value;
  }
  get src() {
    return this._src;
  }
}

beforeEach(() => {
  createdImages = [];
  vi.stubGlobal("Image", FakeImage);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderViewer(index = 0, onIndexChange = vi.fn(), onClose = vi.fn()) {
  render(
    <AssetViewer
      assets={ASSETS}
      index={index}
      onIndexChange={onIndexChange}
      onClose={onClose}
    />,
  );
  return { onIndexChange, onClose };
}

describe("AssetViewer", () => {
  it("renders the active asset's thumbnail first", () => {
    renderViewer(1);
    expect(screen.getByTestId("viewer-image")).toHaveAttribute("src", "/thumb/1");
  });

  it("swaps to the original once it preloads", () => {
    renderViewer(1);
    // The active original preload is created; fire its onload.
    const originalImg = createdImages.find((i) => i.src === "/orig/1");
    expect(originalImg).toBeDefined();
    act(() => {
      originalImg?.onload?.();
    });

    expect(screen.getByTestId("viewer-image")).toHaveAttribute("src", "/orig/1");
  });

  it("navigates with next/prev buttons", () => {
    const { onIndexChange } = renderViewer(1);
    fireEvent.click(screen.getByTestId("viewer-next"));
    expect(onIndexChange).toHaveBeenCalledWith(2);
    fireEvent.click(screen.getByTestId("viewer-prev"));
    expect(onIndexChange).toHaveBeenCalledWith(0);
  });

  it("hides prev at the first asset and next at the last", () => {
    const { unmount } = render(
      <AssetViewer
        assets={ASSETS}
        index={0}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("viewer-prev")).toBeNull();
    expect(screen.getByTestId("viewer-next")).toBeInTheDocument();
    unmount();

    render(
      <AssetViewer
        assets={ASSETS}
        index={2}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("viewer-prev")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer-next")).toBeNull();
  });

  it("navigates with arrow keys", () => {
    const { onIndexChange } = renderViewer(1);
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(onIndexChange).toHaveBeenCalledWith(2);
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(onIndexChange).toHaveBeenCalledWith(0);
  });

  it("closes on Escape and on close button", () => {
    const { onClose } = renderViewer(0);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("viewer-close"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("toggles slideshow play state", () => {
    renderViewer(0);
    const toggle = screen.getByTestId("viewer-slideshow-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });

  it("auto-advances when the slideshow timer fires", () => {
    vi.useFakeTimers();
    try {
      const onIndexChange = vi.fn();
      render(
        <AssetViewer
          assets={ASSETS}
          index={0}
          onIndexChange={onIndexChange}
          onClose={vi.fn()}
          slideshowSeconds={3}
        />,
      );
      fireEvent.click(screen.getByTestId("viewer-slideshow-toggle"));
      vi.advanceTimersByTime(3000);
      expect(onIndexChange).toHaveBeenCalledWith(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("exposes dialog a11y semantics", () => {
    renderViewer(0);
    const viewer = screen.getByTestId("asset-viewer");
    expect(viewer).toHaveAttribute("role", "dialog");
    expect(viewer).toHaveAttribute("aria-modal", "true");
  });

  it("hides the favorite control when onToggleFavorite is not provided", () => {
    renderViewer(0);
    expect(screen.queryByTestId("viewer-favorite")).toBeNull();
  });

  it("shows the favorite control and toggles the active asset", () => {
    const onToggleFavorite = vi.fn();
    render(
      <AssetViewer
        assets={ASSETS}
        index={1}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
        favoriteIds={new Set([0])}
        onToggleFavorite={onToggleFavorite}
      />,
    );
    const fav = screen.getByTestId("viewer-favorite");
    // Asset at index 1 has id 1, which is NOT in the favorite set {0}.
    expect(fav).toHaveAttribute("aria-pressed", "false");
    expect(fav).toHaveAccessibleName(/add favorite/i);
    fireEvent.click(fav);
    expect(onToggleFavorite).toHaveBeenCalledWith(1);
  });

  it("reflects a favorited active asset as pressed", () => {
    render(
      <AssetViewer
        assets={ASSETS}
        index={0}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
        favoriteIds={new Set([0])}
        onToggleFavorite={vi.fn()}
      />,
    );
    const fav = screen.getByTestId("viewer-favorite");
    expect(fav).toHaveAttribute("aria-pressed", "true");
    expect(fav).toHaveAccessibleName(/remove favorite/i);
  });

  it("hides archive/trash controls when their callbacks are absent", () => {
    renderViewer(0);
    expect(screen.queryByTestId("viewer-archive")).toBeNull();
    expect(screen.queryByTestId("viewer-trash")).toBeNull();
  });

  it("archives the active asset and closes the viewer", () => {
    const onArchive = vi.fn();
    const onClose = vi.fn();
    render(
      <AssetViewer
        assets={ASSETS}
        index={1}
        onIndexChange={vi.fn()}
        onClose={onClose}
        onArchive={onArchive}
      />,
    );
    fireEvent.click(screen.getByTestId("viewer-archive"));
    expect(onArchive).toHaveBeenCalledWith(1);
    expect(onClose).toHaveBeenCalled();
  });

  it("moves the active asset to trash and closes the viewer", () => {
    const onTrash = vi.fn();
    const onClose = vi.fn();
    render(
      <AssetViewer
        assets={ASSETS}
        index={0}
        onIndexChange={vi.fn()}
        onClose={onClose}
        onTrash={onTrash}
      />,
    );
    fireEvent.click(screen.getByTestId("viewer-trash"));
    expect(onTrash).toHaveBeenCalledWith(0);
    expect(onClose).toHaveBeenCalled();
  });
});
