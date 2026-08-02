"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type {
  GeoJSONSource,
  Map as MapLibreMap,
  Marker as MapLibreMarker,
  StyleSpecification,
} from "maplibre-gl";
import { useEffect, useRef } from "react";
import type { MapMarker } from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";
import styles from "./private-map.module.css";

const LAND_SOURCE_URL = "/maps/ne_110m_land.geojson";
const PHOTO_SOURCE_ID = "private-photos";
const CLUSTER_LAYER_ID = "private-photo-clusters";
const PHOTO_LAYER_ID = "private-photo-points";

interface PrivateMapProps {
  markers: MapMarker[];
  selectedIds: ReadonlySet<number>;
  onSelect: (ids: number[]) => void;
  fitRequest: number;
}

type MapLibreModule = typeof import("maplibre-gl");
type GeoJsonStyleSource = Extract<
  StyleSpecification["sources"][string],
  { type: "geojson" }
>;
type LandSourceData = GeoJsonStyleSource["data"];

interface RenderedDomMarker {
  marker: MapLibreMarker;
  element: HTMLButtonElement;
}

interface LocalLandFeatureCollection {
  features: Array<{
    geometry?: {
      type?: string;
      coordinates?: unknown;
    } | null;
  }>;
}

function createLandOverlay(
  container: HTMLDivElement,
  map: MapLibreMap,
  landData: LandSourceData,
): { sync: () => void; remove: () => void } {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  const path = document.createElementNS(namespace, "path");
  svg.setAttribute("aria-hidden", "true");
  svg.dataset.mapLandFallback = "true";
  Object.assign(svg.style, {
    position: "absolute",
    inset: "0",
    zIndex: "0",
    width: "100%",
    height: "100%",
    overflow: "hidden",
    pointerEvents: "none",
  });
  path.setAttribute("fill-rule", "evenodd");
  path.setAttribute("stroke-width", "0.75");
  path.setAttribute("vector-effect", "non-scaling-stroke");
  svg.append(path);
  container.append(svg);

  const collection = landData as unknown as LocalLandFeatureCollection;
  const sync = () => {
    const width = container.clientWidth;
    const height = container.clientHeight;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const commands: string[] = [];

    const drawRing = (ring: unknown) => {
      if (!Array.isArray(ring)) return;
      let drewPoint = false;
      for (const coordinate of ring) {
        if (
          !Array.isArray(coordinate) ||
          typeof coordinate[0] !== "number" ||
          typeof coordinate[1] !== "number"
        ) {
          continue;
        }
        const point = map.project([
          coordinate[0],
          Math.max(-85.0511, Math.min(85.0511, coordinate[1])),
        ]);
        commands.push(
          `${drewPoint ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)}`,
        );
        drewPoint = true;
      }
      if (drewPoint) commands.push("Z");
    };

    for (const feature of collection.features ?? []) {
      const geometry = feature.geometry;
      if (!geometry || !Array.isArray(geometry.coordinates)) continue;
      if (geometry.type === "Polygon") {
        for (const ring of geometry.coordinates) drawRing(ring);
      } else if (geometry.type === "MultiPolygon") {
        for (const polygon of geometry.coordinates) {
          if (!Array.isArray(polygon)) continue;
          for (const ring of polygon) drawRing(ring);
        }
      }
    }

    const dark = isDarkMap();
    path.setAttribute("d", commands.join(" "));
    path.setAttribute("fill", dark ? "#172a36" : "#f4efe5");
    path.setAttribute("stroke", dark ? "#355262" : "#b9c5c8");
  };

  sync();
  return { sync, remove: () => svg.remove() };
}

export function mapMarkersToFeatureCollection(markers: readonly MapMarker[]) {
  return {
    type: "FeatureCollection" as const,
    features: (markers ?? []).map((marker) => ({
      type: "Feature" as const,
      geometry: {
        type: "Point" as const,
        coordinates: [marker.lon, marker.lat],
      },
      properties: {
        id: marker.id,
      },
    })),
  };
}

function isDarkMap(): boolean {
  const root = document.documentElement;
  if (root.dataset.theme === "light" || root.classList.contains("light")) {
    return false;
  }
  if (root.dataset.theme === "dark" || root.classList.contains("dark")) {
    return true;
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true;
}

export function buildOfflineMapStyle(
  markers: readonly MapMarker[],
  dark: boolean,
  landData: LandSourceData = LAND_SOURCE_URL,
): StyleSpecification {
  return {
    version: 8,
    sources: {
      "offline-land": {
        type: "geojson",
        data: landData,
      },
      [PHOTO_SOURCE_ID]: {
        type: "geojson",
        data: mapMarkersToFeatureCollection(markers),
        cluster: true,
        clusterMaxZoom: 14,
        clusterRadius: 48,
      },
    },
    layers: [
      {
        id: "offline-ocean",
        type: "background",
        paint: {
          "background-color": dark ? "#07121c" : "#dbeaf1",
        },
      },
      {
        id: "offline-land-fill",
        type: "fill",
        source: "offline-land",
        paint: {
          "fill-color": dark ? "#172a36" : "#f4efe5",
          "fill-opacity": 1,
        },
      },
      {
        id: "offline-land-line",
        type: "line",
        source: "offline-land",
        paint: {
          "line-color": dark ? "#355262" : "#b9c5c8",
          "line-width": 0.75,
          "line-opacity": 0.8,
        },
      },
      {
        id: CLUSTER_LAYER_ID,
        type: "circle",
        source: PHOTO_SOURCE_ID,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#ff801f",
          "circle-radius": [
            "step",
            ["get", "point_count"],
            20,
            10,
            23,
            100,
            27,
          ],
          "circle-opacity": 0.28,
          "circle-stroke-color": "#ffb77e",
          "circle-stroke-width": 1,
        },
      },
      {
        id: PHOTO_LAYER_ID,
        type: "circle",
        source: PHOTO_SOURCE_ID,
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": "#ff801f",
          "circle-radius": 18,
          "circle-opacity": 0.2,
          "circle-stroke-color": "#ffb77e",
          "circle-stroke-width": 1,
        },
      },
    ],
  };
}

/** Return the smallest longitude interval, including across the dateline. */
export function calculateMapBounds(
  markers: readonly MapMarker[],
): [west: number, south: number, east: number, north: number] | null {
  if (markers.length === 0) {
    return null;
  }

  const longitudes = markers
    .map((marker) => ((marker.lon % 360) + 360) % 360)
    .sort((left, right) => left - right);
  let largestGap = -1;
  let gapStartIndex = 0;
  for (let index = 0; index < longitudes.length; index += 1) {
    const current = longitudes[index];
    const next =
      index === longitudes.length - 1
        ? (longitudes[0] ?? 0) + 360
        : longitudes[index + 1];
    if (current === undefined || next === undefined) {
      continue;
    }
    const gap = next - current;
    if (gap > largestGap) {
      largestGap = gap;
      gapStartIndex = index;
    }
  }

  const westIndex = (gapStartIndex + 1) % longitudes.length;
  let west = longitudes[westIndex] ?? markers[0]?.lon ?? 0;
  let east = longitudes[gapStartIndex] ?? west;
  if (east < west) {
    east += 360;
  }
  if (west > 180) {
    west -= 360;
    east -= 360;
  }

  const latitudes = markers.map((marker) => marker.lat);
  return [west, Math.min(...latitudes), east, Math.max(...latitudes)];
}

function fitMarkers(
  map: MapLibreMap,
  maplibre: MapLibreModule,
  markers: readonly MapMarker[],
): void {
  if (markers.length === 0) {
    map.easeTo({ center: [15, 20], zoom: 1.25, duration: 350 });
    return;
  }

  const first = markers[0];
  if (!first) {
    return;
  }
  if (markers.length === 1) {
    map.easeTo({
      center: [first.lon, first.lat],
      zoom: 10,
      duration: 450,
    });
    return;
  }

  const coordinates = calculateMapBounds(markers);
  if (!coordinates) {
    return;
  }
  const [west, south, east, north] = coordinates;
  const bounds = new maplibre.LngLatBounds([west, south], [east, north]);
  map.fitBounds(bounds, {
    padding: 64,
    maxZoom: 11,
    duration: 500,
  });
}

function applyMapPalette(map: MapLibreMap): void {
  if (!map.isStyleLoaded()) {
    return;
  }
  const dark = isDarkMap();
  map.setPaintProperty(
    "offline-ocean",
    "background-color",
    dark ? "#07121c" : "#dbeaf1",
  );
  map.setPaintProperty(
    "offline-land-fill",
    "fill-color",
    dark ? "#172a36" : "#f4efe5",
  );
  map.setPaintProperty(
    "offline-land-line",
    "line-color",
    dark ? "#355262" : "#b9c5c8",
  );
}

export function PrivateMap({
  markers,
  selectedIds,
  onSelect,
  fitRequest,
}: PrivateMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const maplibreRef = useRef<MapLibreModule | null>(null);
  const markersRef = useRef(markers);
  const selectedIdsRef = useRef(selectedIds);
  const onSelectRef = useRef(onSelect);
  const syncMarkersRef = useRef<() => void>(() => {});
  const lastFitRequestRef = useRef(fitRequest);

  markersRef.current = markers;
  selectedIdsRef.current = selectedIds;
  onSelectRef.current = onSelect;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    let disposed = false;
    let themeObserver: MutationObserver | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let landOverlay: ReturnType<typeof createLandOverlay> | null = null;
    const rendered = new Map<string, RenderedDomMarker>();

    void Promise.all([
      import("maplibre-gl"),
      fetch(LAND_SOURCE_URL, { cache: "force-cache" }).then((response) => {
      .catch(err => console.error(err))