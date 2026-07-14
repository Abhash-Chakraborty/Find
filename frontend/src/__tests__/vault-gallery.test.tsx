import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VaultGallery } from "@/components/vault/VaultGallery";
import { vaultStore } from "@/store/vaultStore";

const vaultClient = vi.hoisted(() => ({
  fetchVaultOriginal: vi.fn(),
  fetchVaultThumbnail: vi.fn(),
  listVaultItems: vi.fn(),
  lockVaultSession: vi.fn(),
  restoreVaultItem: vi.fn(),
  changeVaultPassword: vi.fn(),
  getVaultStatus: vi.fn(),
  setupVault: vi.fn(),
  recoverVault: vi.fn(),
  unlockVault: vi.fn(),
}));

vi.mock("@/components/vault/vault-client", () => ({
  ...vaultClient,
  isExpiredVaultSession: () => false,
}));

class FakeResizeObserver {
  constructor(private callback: ResizeObserverCallback) {}

  observe(target: Element) {
    this.callback(
      [
        {
          target,
          contentRect: { width: 1000, height: 0 } as DOMRectReadOnly,
        } as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }

  unobserve() {}
  disconnect() {}
}

const item = {
  id: 7,
  filename: "private-summer.png",
  content_type: "image/png",
  width: 1600,
  height: 900,
  created_at: "2026-07-02T00:00:00Z",
  hidden_at: "2026-07-10T00:00:00Z",
};

function renderVault() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <VaultGallery />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("innerHeight", 5000);
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal(
    "Image",
    class {
      onload: (() => void) | null = null;
      set src(_value: string) {}
    },
  );

  let objectUrlSequence = 0;
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => `blob:vault-${++objectUrlSequence}`),
    revokeObjectURL: vi.fn(),
  });

  vaultStore.getState().unlock("vault-session-token");
  vaultClient.listVaultItems.mockResolvedValue([item]);
  vaultClient.getVaultStatus.mockResolvedValue({
    initialized: true,
    recovery_available: true,
  });
  vaultClient.fetchVaultThumbnail.mockResolvedValue(
    new Blob(["thumbnail"], { type: "image/webp" }),
  );
  vaultClient.fetchVaultOriginal.mockResolvedValue(
    new Blob(["original"], { type: "image/png" }),
  );
  vaultClient.lockVaultSession.mockResolvedValue(undefined);
  vaultClient.restoreVaultItem.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vaultStore.getState().lock();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("VaultGallery", () => {
  it("uses the timeline and fetches no original until its viewer opens", async () => {
    renderVault();

    expect(await screen.findByText("July 2026")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-media-view")).toBeInTheDocument();
    await waitFor(() => {
      expect(vaultClient.fetchVaultThumbnail).toHaveBeenCalledWith(
        item.id,
        "vault-session-token",
      );
    });
    expect(vaultClient.fetchVaultOriginal).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId(`open-vault-item-${item.id}`));

    await waitFor(() => {
      expect(vaultClient.fetchVaultOriginal).toHaveBeenCalledWith(
        item.id,
        "vault-session-token",
      );
    });
    expect(screen.getByTestId("asset-viewer")).toBeInTheDocument();
  });

  it("restores a vault item through the authenticated endpoint", async () => {
    renderVault();

    const restore = await screen.findByRole("button", {
      name: `Restore ${item.filename}`,
    });
    fireEvent.click(restore);

    await waitFor(() => {
      expect(vaultClient.restoreVaultItem).toHaveBeenCalledWith(
        item.id,
        "vault-session-token",
      );
    });
  });

  it("invalidates the server session and clears memory when locked", async () => {
    renderVault();

    fireEvent.click(await screen.findByRole("button", { name: "Lock Vault" }));

    expect(vaultStore.getState().sessionToken).toBeNull();
    await waitFor(() => {
      expect(vaultClient.lockVaultSession).toHaveBeenCalledWith(
        "vault-session-token",
      );
    });
    expect(
      await screen.findByRole("button", { name: /unlock vault/i }),
    ).toBeVisible();
  });
});
