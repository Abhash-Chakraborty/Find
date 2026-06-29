/**
 * Accessibility smoke tests for the new overhaul UI.
 *
 * Uses the existing testing-library role/accessible-name queries (no new
 * framework, per the plan's "add fixtures, not new frameworks" rule) to assert
 * that the new interactive components expose correct ARIA roles and names.
 *
 * NOTE: This is the AUTOMATED portion of Phase 10.5 only. A manual keyboard +
 * screen-reader pass is still required and is NOT replaced by these checks.
 *
 * Run with: pnpm vitest run src/__tests__/a11y-smoke.test.tsx
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AddToAlbumModal } from "@/components/add-to-album-modal";
import { AssetViewer } from "@/components/asset-viewer";
import { HardwareAccelSettings } from "@/components/hardware-accel-settings";
import { TimelineScrubber } from "@/components/timeline-scrubber";

vi.mock("@/lib/api", () => ({
  getHardwareReport: vi.fn().mockResolvedValue({
    accel_mode: "auto",
    capabilities: {
      available_providers: ["CPUExecutionProvider"],
      torch_cuda: false,
      torch_mps: false,
      has_gpu: false,
      best_gpu_provider: null,
    },
    resolved: {
      mode: "auto",
      providers: ["CPUExecutionProvider"],
      using_gpu: false,
      fell_back_to_cpu: false,
      notice: null,
    },
  }),
  getAlbums: vi.fn().mockResolvedValue({ albums: [], total: 0 }),
  createAlbum: vi.fn(),
  addAlbumAssets: vi.fn(),
}));

function withClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    "Image",
    class {
      onload: (() => void) | null = null;
      set src(_v: string) {}
    },
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a11y: AssetViewer", () => {
  const assets = [
    { id: 1, thumbnailUrl: "/t/1", originalUrl: "/o/1" },
    { id: 2, thumbnailUrl: "/t/2", originalUrl: "/o/2" },
  ];

  it("is a labelled modal dialog with labelled controls", () => {
    render(
      <AssetViewer
        assets={assets}
        index={0}
        onIndexChange={() => {}}
        onClose={() => {}}
      />,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName(/image viewer/i);
    // Controls have accessible names (not icon-only with no label).
    expect(
      screen.getByRole("button", { name: /close viewer/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /next image/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /play slideshow|pause slideshow/i }),
    ).toBeInTheDocument();
  });
});

describe("a11y: TimelineScrubber", () => {
  it("exposes a vertical scrollbar role with value semantics", () => {
    render(
      <TimelineScrubber
        buckets={[{ timeBucket: "2026-03-01", count: 5 }]}
        scrollOffset={0}
        onScrub={() => {}}
      />,
    );
    const scrollbar = screen.getByRole("scrollbar");
    expect(scrollbar).toHaveAttribute("aria-orientation", "vertical");
    expect(scrollbar).toHaveAccessibleName(/timeline date scrubber/i);
    expect(scrollbar).toHaveAttribute("aria-valuenow");
  });
});

describe("a11y: HardwareAccelSettings", () => {
  it("labels the section heading and every accel option", async () => {
    withClient(<HardwareAccelSettings />);
    expect(
      screen.getByRole("heading", { name: /hardware acceleration/i }),
    ).toBeInTheDocument();
    // Radio inputs are reachable by their visible labels. Anchor on the
    // leading label token — hints mention other modes (e.g. GPU's hint says
    // "fall back to CPU"), so an unanchored match would be ambiguous.
    for (const name of [/^Auto/, /^GPU/, /^CPU/]) {
      expect(screen.getByRole("radio", { name })).toBeInTheDocument();
    }
  });
});

describe("a11y: AddToAlbumModal", () => {
  it("is a labelled modal dialog with a labelled close control", async () => {
    withClient(
      <AddToAlbumModal mediaIds={[1]} onClose={() => {}} onAdded={() => {}} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName(/add to album/i);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /^close$/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/new album name/i)).toBeInTheDocument();
  });
});
