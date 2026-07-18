import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TimelineMediaView } from "@/components/timeline-media-view";

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

const items = [
  {
    id: 1,
    filename: "march.jpg",
    createdAt: "2026-03-20T00:00:00Z",
    width: 1600,
    height: 900,
  },
  {
    id: 2,
    filename: "february.jpg",
    createdAt: "2026-02-01T00:00:00Z",
    width: 800,
    height: 1200,
  },
];

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("innerHeight", 5000);
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal(
    "Image",
    class {
      onload: (() => void) | null = null;
      set src(_value: string) {}
    },
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderTimeline(action = vi.fn()) {
  render(
    <TimelineMediaView
      items={items}
      getId={(item) => item.id}
      getDate={(item) => item.createdAt}
      getWidth={(item) => item.width}
      getHeight={(item) => item.height}
      getThumbnailUrl={(item) => `/thumb/${item.id}`}
      getOriginalUrl={(item) => `/original/${item.id}`}
      getAlt={(item) => item.filename}
      getOpenTestId={(item) => `open-${item.id}`}
      renderItemActions={(item) => (
        <button type="button" onClick={() => action(item.id)}>
          Act on {item.id}
        </button>
      )}
    />,
  );
  return action;
}

describe("TimelineMediaView", () => {
  it("renders date groups, a linked keyboard scrollbar, and justified items", () => {
    renderTimeline();

    expect(screen.getByText("March 2026")).toBeInTheDocument();
    expect(screen.getByText("February 2026")).toBeInTheDocument();
    expect(screen.getAllByTestId("justified-grid")).toHaveLength(2);

    const scrubber = screen.getByRole("scrollbar", {
      name: "Timeline date scrubber",
    });
    expect(scrubber).toHaveAttribute("tabindex", "0");
    expect(scrubber).toHaveAttribute("aria-controls", "route-media-timeline");
    expect(screen.getByTestId("open-1").tagName).toBe("BUTTON");
  });

  it("opens the canonical AssetViewer from a media tile", () => {
    renderTimeline();
    fireEvent.click(screen.getByTestId("open-1"));

    expect(screen.getByTestId("asset-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("viewer-image")).toHaveAttribute(
      "src",
      "/thumb/1",
    );
  });

  it("keeps route actions independent from opening the viewer", () => {
    const action = renderTimeline();
    fireEvent.click(screen.getByRole("button", { name: "Act on 1" }));

    expect(action).toHaveBeenCalledWith(1);
    expect(screen.queryByTestId("asset-viewer")).toBeNull();
  });
});
