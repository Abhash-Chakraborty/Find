/**
 * Component tests for the TimelineScrubber.
 *
 * jsdom has no layout engine, so we stub getBoundingClientRect on the track to
 * give it a known height. The geometry itself is covered in
 * timeline-scrubber.test.ts; here we verify wiring: thumb position, the
 * floating date label on hover, and that pointer drags call onScrub with the
 * mapped offset.
 *
 * Run with: pnpm vitest run src/__tests__/timeline-scrubber-component.test.tsx
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TimelineScrubber } from "@/components/timeline-scrubber";

const TRACK_TOP = 0;
const TRACK_HEIGHT = 1000;

// heights with these opts: ceil(count/10)*200 ; offsets 0,400 ; total 600
const BUCKETS = [
  { timeBucket: "2026-03-01", count: 20 },
  { timeBucket: "2026-02-01", count: 10 },
];
const OPTS = {
  targetRowHeight: 200,
  gap: 0,
  columnsPerRow: 10,
  headerHeight: 0,
};

function stubTrackRect() {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    top: TRACK_TOP,
    left: 0,
    right: 16,
    bottom: TRACK_HEIGHT,
    width: 16,
    height: TRACK_HEIGHT,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TimelineScrubber", () => {
  it("renders nothing when there are no buckets", () => {
    const { container } = render(
      <TimelineScrubber buckets={[]} scrollOffset={0} onScrub={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("positions the thumb from the current scroll offset", () => {
    // total height 600; offset 300 => 50% down the track.
    render(
      <TimelineScrubber
        buckets={BUCKETS}
        scrollOffset={300}
        onScrub={() => {}}
        layoutOptions={OPTS}
      />,
    );
    const thumb = screen.getByTestId("scrubber-thumb");
    expect(thumb.style.top).toBe("50%");
  });

  it("calls onScrub with the mapped offset on pointer down", () => {
    stubTrackRect();
    const onScrub = vi.fn();
    render(
      <TimelineScrubber
        buckets={BUCKETS}
        scrollOffset={0}
        onScrub={onScrub}
        layoutOptions={OPTS}
      />,
    );

    // Click halfway down the 1000px track => fraction 0.5 => offset 300 of 600.
    fireEvent.pointerDown(screen.getByTestId("timeline-scrubber"), {
      clientY: TRACK_HEIGHT / 2,
      pointerId: 1,
    });

    expect(onScrub).toHaveBeenCalledWith(300);
  });

  it("shows the hovered segment's date label", () => {
    stubTrackRect();
    render(
      <TimelineScrubber
        buckets={BUCKETS}
        scrollOffset={0}
        onScrub={() => {}}
        layoutOptions={OPTS}
      />,
    );

    // Hover near the top => first segment (March 2026).
    fireEvent.pointerMove(screen.getByTestId("timeline-scrubber"), {
      clientY: 10,
      pointerId: 1,
    });

    expect(screen.getByTestId("scrubber-label")).toHaveTextContent(
      "March 2026",
    );
  });

  it("updates onScrub while dragging", () => {
    stubTrackRect();
    const onScrub = vi.fn();
    const scrubber = render(
      <TimelineScrubber
        buckets={BUCKETS}
        scrollOffset={0}
        onScrub={onScrub}
        layoutOptions={OPTS}
      />,
    ).getByTestId("timeline-scrubber");

    fireEvent.pointerDown(scrubber, { clientY: 0, pointerId: 1 });
    fireEvent.pointerMove(scrubber, { clientY: TRACK_HEIGHT, pointerId: 1 });

    // Last call: fraction 1.0 => offset 600.
    expect(onScrub).toHaveBeenLastCalledWith(600);
  });

  it("exposes scrollbar a11y semantics", () => {
    render(
      <TimelineScrubber
        buckets={BUCKETS}
        scrollOffset={0}
        onScrub={() => {}}
        layoutOptions={OPTS}
      />,
    );
    const scrubber = screen.getByTestId("timeline-scrubber");
    expect(scrubber).toHaveAttribute("role", "scrollbar");
    expect(scrubber).toHaveAttribute("aria-orientation", "vertical");
    expect(scrubber).toHaveAttribute("aria-valuetext", "March 2026");
  });

  it("is focusable and declares the region it controls", () => {
    render(
      <TimelineScrubber
        buckets={BUCKETS}
        scrollOffset={0}
        onScrub={() => {}}
        layoutOptions={OPTS}
        controlsId="my-grid"
      />,
    );
    const scrubber = screen.getByTestId("timeline-scrubber");
    // A scrollbar role must be keyboard-focusable and name its target.
    expect(scrubber).toHaveAttribute("tabindex", "0");
    expect(scrubber).toHaveAttribute("aria-controls", "my-grid");
  });

  it("scrubs via the keyboard (End jumps to the bottom)", () => {
    const onScrub = vi.fn();
    render(
      <TimelineScrubber
        buckets={BUCKETS}
        scrollOffset={0}
        onScrub={onScrub}
        layoutOptions={OPTS}
      />,
    );
    // End => fraction 1.0 => offset 600 (total height).
    fireEvent.keyDown(screen.getByTestId("timeline-scrubber"), { key: "End" });
    expect(onScrub).toHaveBeenLastCalledWith(600);
  });

  it("clamps keyboard nudges at the top (ArrowUp at offset 0 stays >= 0)", () => {
    const onScrub = vi.fn();
    render(
      <TimelineScrubber
        buckets={BUCKETS}
        scrollOffset={0}
        onScrub={onScrub}
        layoutOptions={OPTS}
      />,
    );
    fireEvent.keyDown(screen.getByTestId("timeline-scrubber"), {
      key: "ArrowUp",
    });
    // Already at the top → clamped to fraction 0 → offset 0.
    expect(onScrub).toHaveBeenLastCalledWith(0);
  });
});
