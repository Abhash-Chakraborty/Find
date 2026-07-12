import { describe, expect, it } from "vitest";
import {
  buildOfflineMapStyle,
  calculateMapBounds,
  mapMarkersToFeatureCollection,
} from "@/components/private-map";
import type { MapMarker } from "@/lib/api";

const MARKER: MapMarker = {
  id: 42,
  lat: 22.5726,
  lon: 88.3639,
  filename: "local.jpg",
  created_at: "2026-07-12T00:00:00Z",
  thumbnail_url: "/api/image/42/thumbnail",
  ratio: 1.5,
  liked: false,
};

describe("offline private map data", () => {
  it("builds clustered GeoJSON points in longitude-latitude order", () => {
    expect(mapMarkersToFeatureCollection([MARKER])).toEqual({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [88.3639, 22.5726] },
          properties: { id: 42 },
        },
      ],
    });
  });

  it("uses only bundled/local sources and enables client-side clustering", () => {
    const style = buildOfflineMapStyle([MARKER], true);
    const serialized = JSON.stringify(style);

    expect(serialized).toContain("/maps/ne_110m_land.geojson");
    expect(serialized).not.toMatch(/https?:\/\//);
    expect(serialized).not.toContain('"glyphs"');
    expect(serialized).not.toContain('"sprite"');
    expect(serialized).toContain('"cluster":true');
  });

  it("fits nearby dateline photos without zooming out across the world", () => {
    const west = { ...MARKER, id: 1, lon: 179.5 };
    const east = { ...MARKER, id: 2, lon: -179.5 };

    const bounds = calculateMapBounds([west, east]);

    expect(bounds).not.toBeNull();
    expect((bounds?.[2] ?? 0) - (bounds?.[0] ?? 0)).toBeCloseTo(1);
  });
});
