"use client";

import { CalendarDays, Images, X } from "lucide-react";
import { useMemo, useState } from "react";
import { AssetViewer } from "@/components/asset-viewer";
import type { MapMarker } from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";
import { groupMediaByMonth } from "@/lib/media-timeline";
import type { ViewerAsset } from "@/lib/viewer-preload";

interface MapTimelinePanelProps {
  markers: MapMarker[];
  onClose: () => void;
}

export function MapTimelinePanel({ markers, onClose }: MapTimelinePanelProps) {
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const groups = useMemo(
    () => groupMediaByMonth(markers, (marker) => marker.created_at),
    [markers],
  );
  const timelineMarkers = useMemo(
    () => groups.flatMap((group) => group.items),
    [groups],
  );
  const viewerAssets = useMemo<ViewerAsset[]>(
    () =>
      timelineMarkers.map((marker) => ({
        id: marker.id,
        thumbnailUrl:
          resolveMediaUrl(marker.thumbnail_url, null, marker.id, true) ??
          marker.thumbnail_url,
        originalUrl:
          resolveMediaUrl(`/api/image/${marker.id}/original`) ??
          `/api/image/${marker.id}/original`,
        alt: marker.filename,
      })),
    [timelineMarkers],
  );

  let runningIndex = 0;

  return (
    <>
      <aside
        data-testid="map-timeline-panel"
        aria-label="Photos at the selected map location"
        className="flex h-full min-h-[34rem] max-h-[min(72dvh,54rem)] flex-col overflow-hidden rounded-[1.25rem] border border-[color:var(--frost)] bg-[color:var(--void)]/95 shadow-2xl backdrop-blur-xl"
      >
        <header className="flex items-center justify-between gap-3 border-b border-[color:var(--frost)] px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-[color:var(--orange-soft)] text-[color:var(--orange)]">
              <Images aria-hidden="true" size={18} />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold text-[color:var(--near-white)]">
                Selected location
              </h2>
              <p className="text-xs text-[color:var(--muted)]">
                {markers.length.toLocaleString()}{" "}
                {markers.length === 1 ? "photo" : "photos"}
              </p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close selected photo timeline"
            onClick={onClose}
            className="grid size-9 shrink-0 place-items-center rounded-full text-[color:var(--silver)] transition hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--near-white)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
          >
            <X aria-hidden="true" size={18} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pb-4">
          {groups.map((group) => {
            const groupStartIndex = runningIndex;
            runningIndex += group.items.length;
            return (
              <section key={group.timeBucket} className="pb-2">
                <h3 className="sticky top-0 z-10 -mx-1 mb-2 flex items-center gap-2 border-b border-[color:var(--frost)] bg-[color:var(--void)]/92 px-2 py-3 text-xs font-semibold text-[color:var(--silver)] backdrop-blur-lg">
                  <CalendarDays aria-hidden="true" size={14} />
                  {group.label}
                  <span className="ml-auto font-normal text-[color:var(--muted)]">
                    {group.items.length}
                  </span>
                </h3>
                <div className="grid grid-cols-2 gap-2">
                  {group.items.map((marker, index) => (
                    <button
                      key={marker.id}
                      type="button"
                      data-testid={`map-timeline-photo-${marker.id}`}
                      aria-label={`Open ${marker.filename}`}
                      onClick={() => setViewerIndex(groupStartIndex + index)}
                      className="group relative aspect-square overflow-hidden rounded-xl bg-[color:var(--surface-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
                    >
                      {/* biome-ignore lint/performance/noImgElement: authenticated media is served by the local API. */}
                      <img
                        src={
                          resolveMediaUrl(
                            marker.thumbnail_url,
                            null,
                            marker.id,
                            true,
                          ) ?? marker.thumbnail_url
                        }
                        alt={marker.filename}
                        loading="lazy"
                        className="h-full w-full object-cover transition duration-200 group-hover:scale-[1.025]"
                      />
                      <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80 to-transparent px-2 pb-2 pt-6 text-left text-[0.68rem] text-white opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
                        {marker.filename}
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </aside>

      {viewerIndex !== null && viewerAssets[viewerIndex] && (
        <AssetViewer
          assets={viewerAssets}
          index={viewerIndex}
          onIndexChange={setViewerIndex}
          onClose={() => setViewerIndex(null)}
        />
      )}
    </>
  );
}
