import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MapPage from "@/app/map/page";
import type { MapMarker, MapMarkersResponse } from "@/lib/api";

const api = vi.hoisted(() => ({
  getMapMarkers: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getMapMarkers: api.getMapMarkers,
}));

vi.mock("@/components/private-map", () => ({
  PrivateMap: ({
    markers,
    onSelect,
  }: {
    markers: MapMarker[];
    onSelect: (ids: number[]) => void;
  }) => (
    <div data-testid="private-map">
      <span>{markers.length} map markers</span>
      <button
        type="button"
        onClick={() => onSelect(markers.map(({ id }) => id))}
      >
        Select map cluster
      </button>
    </div>
  ),
}));

const MARKERS: MapMarker[] = [
  {
    id: 1,
    lat: 22.5726,
    lon: 88.3639,
    filename: "kolkata.jpg",
    created_at: "2026-07-11T10:00:00Z",
    thumbnail_url: "/api/image/1/thumbnail",
    ratio: 1.5,
    liked: true,
  },
  {
    id: 2,
    lat: 51.5072,
    lon: -0.1276,
    filename: "london.jpg",
    created_at: "2026-06-05T10:00:00Z",
    thumbnail_url: "/api/image/2/thumbnail",
    ratio: 1,
    liked: false,
  },
];

function enabledResponse(markers = MARKERS): MapMarkersResponse {
  return { enabled: true, markers, total: markers.length };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MapPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.getMapMarkers.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("MapPage", () => {
  it("shows the opt-in state and links directly to map privacy settings", async () => {
    api.getMapMarkers.mockResolvedValue({
      enabled: false,
      markers: [],
      total: 0,
    } satisfies MapMarkersResponse);

    renderPage();

    const disabled = await screen.findByTestId("map-disabled");
    expect(disabled).toHaveTextContent(/off/i);
    expect(
      screen.getByRole("link", { name: /open map privacy settings/i }),
    ).toHaveAttribute("href", "/settings#private-map");
    expect(screen.queryByTestId("private-map")).toBeNull();
  });

  it("loads clustered-map data and applies favorites and archive filters", async () => {
    api.getMapMarkers.mockResolvedValue(enabledResponse());
    renderPage();

    expect(await screen.findByTestId("private-map")).toHaveTextContent(
      "2 map markers",
    );
    fireEvent.click(screen.getByTestId("map-favorites-filter"));

    await waitFor(() =>
      expect(api.getMapMarkers).toHaveBeenCalledWith({
        liked: true,
        includeArchived: false,
      }),
    );

    fireEvent.click(screen.getByTestId("map-archive-filter"));
    await waitFor(() =>
      expect(api.getMapMarkers).toHaveBeenCalledWith({
        liked: true,
        includeArchived: true,
      }),
    );
  });

  it("opens a month timeline for a selected cluster and uses original media in the viewer", async () => {
    const preloaded: string[] = [];
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        set src(value: string) {
          preloaded.push(value);
        }
      },
    );
    api.getMapMarkers.mockResolvedValue(enabledResponse());
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: "Select map cluster" }),
    );

    expect(screen.getByTestId("map-timeline-panel")).toHaveTextContent(
      "2 photos",
    );
    expect(screen.getByText("July 2026")).toBeInTheDocument();
    expect(screen.getByText("June 2026")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("map-timeline-photo-1"));
    expect(screen.getByTestId("asset-viewer")).toBeInTheDocument();
    await waitFor(() =>
      expect(preloaded).toContain("http://localhost:8000/api/image/1/original"),
    );
  });

  it("renders a useful empty state without hiding the offline world map", async () => {
    api.getMapMarkers.mockResolvedValue(enabledResponse([]));
    renderPage();

    expect(await screen.findByTestId("private-map")).toBeInTheDocument();
    expect(screen.getByTestId("map-empty")).toHaveTextContent(
      /no matching photos/i,
    );
  });
});
