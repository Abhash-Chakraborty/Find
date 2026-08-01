"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  Heart,
  LocateFixed,
  MapPinned,
  MapPinOff,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { type ReactNode, useMemo, useState } from "react";
import { MapTimelinePanel } from "@/components/map-timeline-panel";
import { PrivateMap } from "@/components/private-map";
import { getMapMarkers } from "@/lib/api";

function FilterButton({
  active,
  label,
  icon,
  onClick,
  testId,
}: {
  active: boolean;
  label: string;
  icon: ReactNode;
  onClick: () => void;
  testId: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={active}
      onClick={onClick}
      className="inline-flex h-10 items-center gap-2 rounded-full border border-[color:var(--frost)] bg-[color:var(--surface-soft)] px-3 text-xs font-semibold text-[color:var(--silver)] transition hover:border-[color:var(--frost-strong)] hover:text-[color:var(--near-white)] aria-pressed:border-[color:var(--orange)] aria-pressed:bg-[color:var(--orange-soft)] aria-pressed:text-[color:var(--near-white)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
    >
      {icon}
      {label}
    </button>
  );
}

export default function MapPage() {
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [fitRequest, setFitRequest] = useState(0);

  const markersQuery = useQuery({
    queryKey: ["map-markers", { onlyFavorites, includeArchived }],
    queryFn: () =>
      getMapMarkers({
        liked: onlyFavorites ? true : undefined,
        includeArchived,
      }),
    retry: false,
    refetchOnMount: "always",
    placeholderData: (previousData) => previousData,
  });

  const markers = markersQuery.data?.markers ?? [];
  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const selectedMarkers = useMemo(
    () => markers.filter((marker) => selectedIdSet.has(marker.id)),
    [markers, selectedIdSet],
  );

  return (
    <main className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <header className="mb-5 flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-[color:var(--orange)]">
            <ShieldCheck aria-hidden="true" size={15} />
            Private and offline
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--near-white)] sm:text-4xl">
            Photo map
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--silver)]">
            Explore the locations already embedded in your photos. Find uses a
            bundled world map and never contacts a tile provider or geocoder.
          </p>
        </div>

        {markersQuery.data?.enabled && (
          <fieldset className="flex flex-wrap items-center gap-2">
            <legend className="sr-only">Map filters</legend>
            <FilterButton
              active={onlyFavorites}
              label="Favorites"
              icon={<Heart aria-hidden="true" size={15} />}
              onClick={() => {
                setOnlyFavorites((value) => !value);
                setSelectedIds([]);
              }}
              testId="map-favorites-filter"
            />
            <FilterButton
              active={includeArchived}
              label="Include archive"
              icon={<Archive aria-hidden="true" size={15} />}
              onClick={() => {
                setIncludeArchived((value) => !value);
                setSelectedIds([]);
              }}
              testId="map-archive-filter"
            />
            <button
              type="button"
              data-testid="map-fit-all"
              onClick={() => setFitRequest((value) => value + 1)}
              className="inline-flex h-10 items-center gap-2 rounded-full border border-[color:var(--frost)] bg-[color:var(--surface-soft)] px-3 text-xs font-semibold text-[color:var(--silver)] transition hover:border-[color:var(--frost-strong)] hover:text-[color:var(--near-white)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
            >
              <LocateFixed aria-hidden="true" size={15} />
              Fit all
            </button>
          </fieldset>
        )}
      </header>

      {markersQuery.isPending ? (
        <section
          data-testid="map-loading"
          aria-label="Loading photo map"
          className="grid min-h-[34rem] place-items-center rounded-[1.25rem] border border-[color:var(--frost)] bg-[color:var(--surface-soft)]"
        >
          <div className="flex items-center gap-3 text-sm text-[color:var(--silver)]">
            <RefreshCw aria-hidden="true" className="animate-spin" size={18} />
            Loading private map…
          </div>
        </section>
      ) : markersQuery.isError ? (
        <section
          data-testid="map-error"
          role="alert"
          className="grid min-h-[28rem] place-items-center rounded-[1.25rem] border border-[color:var(--red)]/30 bg-[color:var(--red-soft)] p-8 text-center"
        >
          <div>
            <MapPinOff
              aria-hidden="true"
              className="mx-auto text-[color:var(--red)]"
              size={32}
            />
            <h2 className="mt-4 text-lg font-semibold">Map could not load</h2>
            <p className="mt-2 text-sm text-[color:var(--silver)]">
              Your photos are unchanged. Retry the local API request.
            </p>
            <button
              type="button"
              onClick={() => markersQuery.refetch()}
              className="mt-5 rounded-xl bg-[color:var(--near-white)] px-4 py-2 text-sm font-semibold text-[color:var(--void)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
            >
              Retry
            </button>
          </div>
        </section>
      ) : !markersQuery.data.enabled ? (
        <section
          data-testid="map-disabled"
          className="relative isolate grid min-h-[34rem] overflow-hidden rounded-[1.25rem] border border-[color:var(--frost)] bg-[color:var(--surface-soft)] p-8 sm:p-12"
        >
          <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_70%_20%,var(--orange-soft),transparent_32rem)]" />
          <div className="m-auto max-w-xl text-center">
            <span className="mx-auto grid size-16 place-items-center rounded-2xl border border-[color:var(--frost)] bg-[color:var(--void)] text-[color:var(--orange)] shadow-xl">
              <MapPinned aria-hidden="true" size={28} />
            </span>
            <h2 className="mt-6 text-2xl font-semibold text-[color:var(--near-white)]">
              Your private map is off
            </h2>
            <p className="mt-3 text-sm leading-6 text-[color:var(--silver)]">
              Location extraction is opt-in. Enable it in Settings, then upload
              new photos or reprocess existing ones to read local EXIF GPS.
              Online map tiles and reverse geocoding remain disabled.
            </p>
            <Link
              href="/settings#private-map"
              className="mt-6 inline-flex h-11 items-center rounded-xl bg-[color:var(--near-white)] px-5 text-sm font-semibold text-[color:var(--void)] transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
            >
              Open map privacy settings
            </Link>
          </div>
        </section>
      ) : (
        <>
          <div
            className={`grid items-stretch gap-4 ${
              selectedMarkers.length > 0
                ? "xl:grid-cols-[minmax(0,2fr)_minmax(18rem,0.8fr)]"
                : "grid-cols-1"
            }`}
          >
            <div className="min-w-0">
              <PrivateMap
                markers={markers}
                selectedIds={selectedIdSet}
                onSelect={setSelectedIds}
                fitRequest={fitRequest}
              />
            </div>
            {selectedMarkers.length > 0 && (
              <MapTimelinePanel
                markers={selectedMarkers}
                onClose={() => setSelectedIds([])}
              />
            )}
          </div>

          {markers.length === 0 && (
            <div
              data-testid="map-empty"
              className="mt-4 flex items-start gap-3 rounded-xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)] p-4 text-sm text-[color:var(--silver)]"
            >
              <MapPinOff
                aria-hidden="true"
                className="mt-0.5 shrink-0 text-[color:var(--orange)]"
                size={18}
              />
              <p>
                No matching photos have GPS metadata yet. Upload a geotagged
                photo or reprocess an existing one after enabling the map.
              </p>
            </div>
          )}

          <footer className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-[0.7rem] text-[color:var(--muted)]">
            <span data-testid="map-total">
              {markersQuery.data.total.toLocaleString()} mapped{" "}
              {markersQuery.data.total === 1 ? "photo" : "photos"}
            </span>
            <span>
              Bundled Natural Earth land geometry · local API data only
            </span>
          </footer>
        </>
      )}
    </main>
  );
}
