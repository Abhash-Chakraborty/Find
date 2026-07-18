"use client";

/**
 * Timeline date-scrubber — the fast date-scrollbar on the timeline's right edge.
 *
 * Shows a draggable thumb whose position reflects the current scroll offset, a
 * floating date label while scrubbing/hovering, and jumps the timeline when the
 * user clicks or drags the track. All geometry (offset<->date<->track-fraction)
 * lives in `@/lib/timeline-scrubber` and is unit-tested separately; this
 * component owns pointer handling and rendering only.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import {
  buildScrubberLayout,
  offsetToSegment,
  offsetToTrackFraction,
  type ScrubberBucketInput,
  type ScrubberOptions,
  trackFractionToOffset,
  trackFractionToSegment,
} from "@/lib/timeline-scrubber";

interface TimelineScrubberProps {
  buckets: ScrubberBucketInput[];
  /** Current scroll offset (px) within the timeline. */
  scrollOffset: number;
  /** Called with a target scroll offset (px) when the user jumps. */
  onScrub: (offset: number) => void;
  layoutOptions?: ScrubberOptions;
  className?: string;
  /**
   * id of the scrollable region this scrollbar controls. Required by the
   * `scrollbar` ARIA role (aria-controls); the timeline page sets it on the
   * grid wrapper so AT announces what the scrubber moves.
   */
  controlsId?: string;
}

// Keyboard step sizes as a fraction of the whole track (scrollbar semantics).
const ARROW_STEP = 0.02;
const PAGE_STEP = 0.1;

export function TimelineScrubber({
  buckets,
  scrollOffset,
  onScrub,
  layoutOptions,
  className,
  controlsId = "timeline-scroll-region",
}: TimelineScrubberProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [hoverFraction, setHoverFraction] = useState<number | null>(null);

  const layout = useMemo(
    () => buildScrubberLayout(buckets, layoutOptions),
    [buckets, layoutOptions],
  );

  const thumbFraction = offsetToTrackFraction(layout, scrollOffset);

  // The label reflects the hovered position while interacting, else the
  // segment at the current scroll offset.
  const activeSegment =
    hoverFraction !== null
      ? trackFractionToSegment(layout, hoverFraction)
      : offsetToSegment(layout, scrollOffset);

  const fractionFromEvent = useCallback((clientY: number): number => {
    const track = trackRef.current;
    if (!track) {
      return 0;
    }
    const rect = track.getBoundingClientRect();
    if (rect.height <= 0) {
      return 0;
    }
    return (clientY - rect.top) / rect.height;
  }, []);

  const scrubTo = useCallback(
    (clientY: number) => {
      const fraction = fractionFromEvent(clientY);
      setHoverFraction(fraction);
      onScrub(trackFractionToOffset(layout, fraction));
    },
    [fractionFromEvent, layout, onScrub],
  );

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      event.currentTarget.setPointerCapture?.(event.pointerId);
      setIsScrubbing(true);
      scrubTo(event.clientY);
    },
    [scrubTo],
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const fraction = fractionFromEvent(event.clientY);
      setHoverFraction(fraction);
      if (isScrubbing) {
        onScrub(trackFractionToOffset(layout, fraction));
      }
    },
    [fractionFromEvent, isScrubbing, layout, onScrub],
  );

  const endScrub = useCallback(() => setIsScrubbing(false), []);

  // Keyboard operation: a focusable scrollbar must be drivable without a
  // pointer. Arrows nudge, PageUp/Down jump, Home/End go to the ends.
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      const current = offsetToTrackFraction(layout, scrollOffset);
      let next: number | null = null;
      switch (event.key) {
        case "ArrowDown":
        case "ArrowRight":
          next = current + ARROW_STEP;
          break;
        case "ArrowUp":
        case "ArrowLeft":
          next = current - ARROW_STEP;
          break;
        case "PageDown":
          next = current + PAGE_STEP;
          break;
        case "PageUp":
          next = current - PAGE_STEP;
          break;
        case "Home":
          next = 0;
          break;
        case "End":
          next = 1;
          break;
        default:
          return;
      }
      event.preventDefault();
      const clamped = Math.min(1, Math.max(0, next));
      onScrub(trackFractionToOffset(layout, clamped));
    },
    [layout, onScrub, scrollOffset],
  );

  if (layout.segments.length === 0) {
    return null;
  }

  const showLabel = (isScrubbing || hoverFraction !== null) && activeSegment;
  const labelFraction = hoverFraction ?? thumbFraction;

  return (
    <div
      ref={trackRef}
      className={className}
      style={{
        position: "relative",
        width: 16,
        height: "100%",
        cursor: "ns-resize",
        touchAction: "none",
      }}
      // A scrollbar role must be focusable and operable by keyboard.
      tabIndex={0}
      role="scrollbar"
      aria-orientation="vertical"
      aria-label="Timeline date scrubber"
      aria-controls={controlsId}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(thumbFraction * 100)}
      aria-valuetext={activeSegment?.label}
      data-testid="timeline-scrubber"
      onKeyDown={handleKeyDown}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endScrub}
      onPointerCancel={endScrub}
      onPointerLeave={() => {
        if (!isScrubbing) {
          setHoverFraction(null);
        }
      }}
    >
      {/* Thumb */}
      <div
        data-testid="scrubber-thumb"
        style={{
          position: "absolute",
          top: `${thumbFraction * 100}%`,
          left: 0,
          right: 0,
          height: 8,
          transform: "translateY(-50%)",
          borderRadius: 4,
          background: "currentColor",
          opacity: isScrubbing ? 0.9 : 0.5,
        }}
      />
      {/* Floating date label */}
      {showLabel && (
        <div
          data-testid="scrubber-label"
          style={{
            position: "absolute",
            top: `${labelFraction * 100}%`,
            right: 24,
            transform: "translateY(-50%)",
            whiteSpace: "nowrap",
            pointerEvents: "none",
          }}
        >
          {activeSegment.label}
        </div>
      )}
    </div>
  );
}
