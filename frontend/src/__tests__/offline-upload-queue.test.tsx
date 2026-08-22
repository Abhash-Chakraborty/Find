/**
 * Component tests for the offline upload queue panel (#259).
 *
 * The panel is rendered from props rather than from the hook so these cases
 * exercise the presentation contract -- when it appears, what it says, and
 * which controls are reachable -- without an IndexedDB round trip. The storage
 * behaviour has its own suite in offline-queue.test.ts.
 *
 * Run with: pnpm vitest run src/__tests__/offline-upload-queue.test.tsx
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OfflineUploadQueue } from "@/components/offline-upload-queue";
import type { QueuedUpload } from "@/lib/offline-queue";

afterEach(cleanup);

function queuedItem(overrides: Partial<QueuedUpload> = {}): QueuedUpload {
  return {
    id: "item-1",
    name: "holiday.jpg",
    size: 2_400_000,
    type: "image/jpeg",
    lastModified: 1_700_000_000_000,
    queuedAt: 1_700_000_000_000,
    seq: 1,
    attempts: 0,
    status: "queued",
    ...overrides,
  };
}

function renderPanel(
  overrides: Partial<React.ComponentProps<typeof OfflineUploadQueue>> = {},
) {
  const props = {
    items: [] as QueuedUpload[],
    online: true,
    flushing: false,
    available: true,
    refresh: vi.fn(),
    flush: vi.fn(),
    remove: vi.fn(),
    clear: vi.fn(),
    ...overrides,
  };
  render(<OfflineUploadQueue {...props} />);
  return props;
}

describe("visibility", () => {
  it("renders nothing when online with an empty queue", () => {
    const { container } = render(
      <OfflineUploadQueue
        items={[]}
        online
        flushing={false}
        available
        refresh={vi.fn()}
        flush={vi.fn()}
        remove={vi.fn()}
        clear={vi.fn()}
      />,
    );
    // The normal path must look exactly as it did before this feature.
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when IndexedDB is unavailable", () => {
    const { container } = render(
      <OfflineUploadQueue
        items={[queuedItem()]}
        online={false}
        flushing={false}
        available={false}
        refresh={vi.fn()}
        flush={vi.fn()}
        remove={vi.fn()}
        clear={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("announces the disconnected state even with nothing queued", () => {
    renderPanel({ online: false });
    expect(
      screen.getByRole("heading", { name: "Offline" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Nothing has been sent yet/i)).toBeInTheDocument();
  });

  it("stays visible while a queue drains after reconnecting", () => {
    renderPanel({ online: true, items: [queuedItem()] });
    expect(
      screen.getByRole("heading", { name: "Waiting to upload" }),
    ).toBeInTheDocument();
  });
});

describe("queued files", () => {
  it("lists each staged file with a human-readable size", () => {
    renderPanel({ online: false, items: [queuedItem()] });
    expect(screen.getByText("holiday.jpg")).toBeInTheDocument();
    expect(screen.getByText(/2\.3 MB/)).toBeInTheDocument();
    expect(screen.getByText("1 file")).toBeInTheDocument();
  });

  it("pluralises the file count", () => {
    renderPanel({
      online: false,
      items: [
        queuedItem(),
        queuedItem({ id: "item-2", name: "b.jpg", seq: 2 }),
      ],
    });
    expect(screen.getByText("2 files")).toBeInTheDocument();
  });

  it("surfaces failed attempts and the last error", () => {
    renderPanel({
      online: false,
      items: [queuedItem({ attempts: 2, lastError: "Network Error" })],
    });
    expect(screen.getByText(/2 failed attempts/)).toBeInTheDocument();
    expect(screen.getByText(/Network Error/)).toBeInTheDocument();
  });

  it("removes a single file", () => {
    const props = renderPanel({ online: false, items: [queuedItem()] });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Remove holiday.jpg from the upload queue",
      }),
    );

    expect(props.remove).toHaveBeenCalledWith("item-1");
  });

  it("clears the whole queue", () => {
    const props = renderPanel({ online: false, items: [queuedItem()] });

    fireEvent.click(
      screen.getByRole("button", { name: "Remove all queued files" }),
    );

    expect(props.clear).toHaveBeenCalled();
  });
});

describe("retry control", () => {
  it("is disabled while offline", () => {
    renderPanel({ online: false, items: [queuedItem()] });
    expect(
      screen.getByRole("button", { name: "Retry queued uploads now" }),
    ).toBeDisabled();
  });

  it("is disabled while a flush is already running", () => {
    renderPanel({ online: true, flushing: true, items: [queuedItem()] });
    expect(
      screen.getByRole("button", { name: "Retry queued uploads now" }),
    ).toBeDisabled();
  });

  it("triggers a flush when online and idle", () => {
    const props = renderPanel({ online: true, items: [queuedItem()] });

    fireEvent.click(
      screen.getByRole("button", { name: "Retry queued uploads now" }),
    );

    expect(props.flush).toHaveBeenCalled();
  });
});
