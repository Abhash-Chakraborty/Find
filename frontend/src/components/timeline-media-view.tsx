"use client";

/**
 * Route-agnostic, date-grouped media timeline.
 *
 * Its month sections, justified rows, fast date scrubber, and scroll-position
 * mapping are adapted from the AGPL-3.0 reference project's timeline behavior.
 * Original copyright belongs to its authors. This file is part of Find and is
 * distributed under AGPL-3.0. See NOTICE.
 */

import {
  type ReactNode,
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AssetViewer } from "@/components/asset-viewer";
import { JustifiedGrid } from "@/components/justified-grid";
import { TimelineScrubber } from "@/components/timeline-scrubber";
import { resolveMediaUrl } from "@/lib/media";
import {
  actualOffsetToScrubberOffset,
  groupMediaByMonth,
  mediaAspectRatio,
  scrubberOffsetToActualOffset,
  type TimelineSectionMeasurement,
  timelineBucketsFromGroups,
} from "@/lib/media-timeline";
import {
  buildScrubberLayout,
  type ScrubberOptions,
} from "@/lib/timeline-scrubber";
import type { ViewerAsset } from "@/lib/viewer-preload";

const SCROLL_ANCHOR_PX = 96;

function resolveApiRoute(url: string | null | undefined) {
  return url?.startsWith("/api/") ? resolveMediaUrl(url) : url;
}

export interface TimelineMediaViewerRenderProps<T> {
  items: T[];
  viewerAssets: ViewerAsset[];
  index: number;
  onIndexChange: (index: number) => void;
  onClose: () => void;
}

interface TimelineMediaViewProps<T> {
  items: readonly T[];
  getId: (item: T) => number;
  getDate: (item: T) => string | null | undefined;
  getWidth?: (item: T) => number | null | undefined;
  getHeight?: (item: T) => number | null | undefined;
  getThumbnailUrl: (item: T) => string | null | undefined;
  getOriginalUrl: (item: T) => string | null | undefined;
  getAlt?: (item: T) => string;
  getOpenLabel?: (item: T) => string;
  getItemTestId?: (item: T) => string;
  getOpenTestId?: (item: T) => string;
  onOpenItem?: (item: T, index: number) => void;
  renderItemActions?: (item: T) => ReactNode;
  renderViewer?: (props: TimelineMediaViewerRenderProps<T>) => ReactNode;
  order?: "newest" | "oldest";
  empty?: ReactNode;
  className?: string;
  controlsId?: string;
  scrollContainerRef?: RefObject<HTMLElement | null>;
}

function useResponsiveRowHeight(): number {
  const [rowHeight, setRowHeight] = useState(220);

  useEffect(() => {
    const update = () => setRowHeight(window.innerWidth < 768 ? 120 : 220);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return rowHeight;
}

export function TimelineMediaView<T>({
  items,
  getId,
  getDate,
  getWidth = () => null,
  getHeight = () => null,
  getThumbnailUrl,
  getOriginalUrl,
  getAlt,
  getOpenLabel,
  getItemTestId,
  getOpenTestId,
  onOpenItem,
  renderItemActions,
  renderViewer,
  order = "newest",
  empty,
  className,
  controlsId = "route-media-timeline",
  scrollContainerRef,
}: TimelineMediaViewProps<T>) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = useRef(new Map<string, HTMLElement>());
  const [scrollOffset, setScrollOffset] = useState(0);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const targetRowHeight = useResponsiveRowHeight();

  const groups = useMemo(
    () => groupMediaByMonth(items, getDate, order),
    [getDate, items, order],
  );
  const timelineItems = useMemo(
    () => groups.flatMap((group) => group.items),
    [groups],
  );
  const buckets = useMemo(() => timelineBucketsFromGroups(groups), [groups]);
  const layoutOptions = useMemo<ScrubberOptions>(
    () => ({
      columnsPerRow: targetRowHeight <= 120 ? 3 : 5,
      gap: 6,
      headerHeight: 44,
      targetRowHeight,
    }),
    [targetRowHeight],
  );
  const scrubberLayout = useMemo(
    () => buildScrubberLayout(buckets, layoutOptions),
    [buckets, layoutOptions],
  );

  const viewerAssets = useMemo<ViewerAsset[]>(
    () =>
      timelineItems.map((item) => {
        const id = getId(item);
        const rawThumbnailUrl = getThumbnailUrl(item);
        const thumbnailUrl = resolveApiRoute(rawThumbnailUrl) ?? "";
        const rawOriginalUrl = getOriginalUrl(item);
        return {
          id,
          thumbnailUrl,
          alt: getAlt?.(item),
          // View-only shares deliberately fall back to their share-scoped
          // thumbnail; a private route is never synthesized here.
          originalUrl: resolveApiRoute(rawOriginalUrl) ?? thumbnailUrl,
        };
      }),
    [getAlt, getId, getOriginalUrl, getThumbnailUrl, timelineItems],
  );

  const measurements = useCallback((): TimelineSectionMeasurement[] => {
    const root = rootRef.current;
    if (!root || typeof window === "undefined") {
      return [];
    }

    const rootTop = root.getBoundingClientRect().top;
    return groups.flatMap((group) => {
      const section = sectionRefs.current.get(group.timeBucket);
      if (!section) {
        return [];
      }
      const rect = section.getBoundingClientRect();
      return [
        {
          timeBucket: group.timeBucket,
          top: rect.top - rootTop,
          height: Math.max(rect.height, section.offsetHeight),
        },
      ];
    });
  }, [groups]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const update = () => {
      const root = rootRef.current;
      if (!root) {
        return;
      }
      const container = scrollContainerRef?.current;
      const rootTop = container
        ? root.getBoundingClientRect().top -
          container.getBoundingClientRect().top +
          container.scrollTop
        : root.getBoundingClientRect().top + window.scrollY;
      const scrollPosition = container?.scrollTop ?? window.scrollY;
      const actualOffset = scrollPosition + SCROLL_ANCHOR_PX - rootTop;
      setScrollOffset(
        actualOffsetToScrubberOffset(
          measurements(),
          scrubberLayout,
          actualOffset,
        ),
      );
    };

    const scrollTarget = scrollContainerRef?.current ?? window;
    update();
    scrollTarget.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      scrollTarget.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [measurements, scrollContainerRef, scrubberLayout]);

  useEffect(() => {
    if (
      viewerIndex !== null &&
      (viewerIndex < 0 || viewerIndex >= timelineItems.length)
    ) {
      setViewerIndex(null);
    }
  }, [timelineItems.length, viewerIndex]);

  const handleScrub = useCallback(
    (nextOffset: number) => {
      const root = rootRef.current;
      if (!root || typeof window === "undefined") {
        return;
      }

      const actualOffset = scrubberOffsetToActualOffset(
        measurements(),
        scrubberLayout,
        nextOffset,
      );
      const container = scrollContainerRef?.current;
      const rootTop = container
        ? root.getBoundingClientRect().top -
          container.getBoundingClientRect().top +
          container.scrollTop
        : root.getBoundingClientRect().top + window.scrollY;
      setScrollOffset(nextOffset);
      const top = Math.max(0, rootTop + actualOffset - SCROLL_ANCHOR_PX);
      if (container) container.scrollTo({ top, behavior: "auto" });
      else window.scrollTo({ top, behavior: "auto" });
    },
    [measurements, scrollContainerRef, scrubberLayout],
  );

  if (timelineItems.length === 0) {
    return <>{empty}</>;
  }

  let runningIndex = 0;

  return (
    <>
      <div
        ref={rootRef}
        id={controlsId}
        data-testid="timeline-media-view"
        className={className}
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 24px",
          alignItems: "start",
          gap: 8,
          scrollMarginTop: SCROLL_ANCHOR_PX,
        }}
      >
        <div style={{ minWidth: 0 }}>
          {groups.map((group) => {
            const groupStartIndex = runningIndex;
            runningIndex += group.items.length;

            return (
              <section
                key={group.timeBucket}
                ref={(element) => {
                  if (element) {
                    sectionRefs.current.set(group.timeBucket, element);
                  } else {
                    sectionRefs.current.delete(group.timeBucket);
                  }
                }}
                data-testid={`timeline-group-${group.timeBucket}`}
                aria-labelledby={`timeline-heading-${group.timeBucket}`}
                style={{ marginBottom: 28, scrollMarginTop: SCROLL_ANCHOR_PX }}
              >
                <h2
                  id={`timeline-heading-${group.timeBucket}`}
                  className="mb-3 border-b border-[var(--frost)] bg-[color:var(--void)]/90 py-2 text-sm font-semibold text-[color:var(--near-white)] backdrop-blur-md"
                  style={{
                    position: "sticky",
                    top: "var(--nav-height)",
                    zIndex: 5,
                  }}
                >
                  {group.label}
                  <span className="ml-2 text-xs font-normal text-[color:var(--muted)]">
                    {group.items.length}
                  </span>
                </h2>
                <JustifiedGrid
                  scrollContainerRef={scrollContainerRef}
                  items={group.items.map((item) => ({
                    item,
                    ratio: mediaAspectRatio(getWidth(item), getHeight(item)),
                  }))}
                  targetRowHeight={targetRowHeight}
                  gap={6}
                  getKey={({ item }) => getId(item)}
                  renderItem={({ item }, index) => {
                    const timelineIndex = groupStartIndex + index;
                    const rawThumbnailUrl = getThumbnailUrl(item);
                    const thumbnailUrl = resolveApiRoute(rawThumbnailUrl);
                    return (
                      <article
                        data-testid={getItemTestId?.(item)}
                        className="group relative h-full w-full overflow-hidden rounded-lg bg-[color:var(--surface-soft)]"
                      >
                        <button
                          type="button"
                          data-testid={getOpenTestId?.(item)}
                          aria-label={
                            getOpenLabel?.(item) ??
                            `Open ${getAlt?.(item) || "image"}`
                          }
                          onClick={() => {
                            if (onOpenItem) onOpenItem(item, timelineIndex);
                            else setViewerIndex(timelineIndex);
                          }}
                          className="block h-full w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)] focus-visible:ring-inset"
                        >
                          {thumbnailUrl ? (
                            // biome-ignore lint/performance/noImgElement: authenticated and share-scoped media URLs are not Next image assets.
                            <img
                              src={thumbnailUrl}
                              alt={getAlt?.(item) ?? `Photo ${getId(item)}`}
                              loading="lazy"
                              className="h-full w-full object-cover transition duration-200 group-hover:scale-[1.015]"
                            />
                          ) : (
                            <span className="grid h-full w-full place-items-center text-xs text-[color:var(--muted)]">
                              No preview
                            </span>
                          )}
                        </button>
                        {renderItemActions && (
                          <div className="absolute inset-x-0 bottom-0 flex justify-end gap-1 bg-gradient-to-t from-black/70 to-transparent p-2 opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                            {renderItemActions(item)}
                          </div>
                        )}
                      </article>
                    );
                  }}
                />
              </section>
            );
          })}
        </div>

        <aside
          aria-label="Timeline navigation"
          style={{
            position: "sticky",
            top: scrollContainerRef ? 12 : "calc(var(--nav-height) + 12px)",
            height: scrollContainerRef
              ? "calc(90dvh - 140px)"
              : "calc(100dvh - var(--nav-height) - 24px)",
            zIndex: 10,
          }}
          className="text-[color:var(--silver)]"
        >
          <TimelineScrubber
            buckets={buckets}
            scrollOffset={scrollOffset}
            onScrub={handleScrub}
            layoutOptions={layoutOptions}
            controlsId={controlsId}
          />
        </aside>
      </div>

      {viewerIndex !== null &&
        viewerAssets[viewerIndex] &&
        (renderViewer ? (
          renderViewer({
            items: timelineItems,
            viewerAssets,
            index: viewerIndex,
            onIndexChange: setViewerIndex,
            onClose: () => setViewerIndex(null),
          })
        ) : (
          <AssetViewer
            assets={viewerAssets}
            index={viewerIndex}
            onIndexChange={setViewerIndex}
            onClose={() => setViewerIndex(null)}
          />
        ))}
    </>
  );
}
