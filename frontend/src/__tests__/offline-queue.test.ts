/**
 * Offline upload queue (#259).
 *
 * The behaviour worth protecting here is not "can we write to IndexedDB" but
 * the three things that make a resume-on-reconnect queue safe: it must not send
 * a file twice, it must not lose one when a send fails, and it must never hold
 * a secret.
 */

import "fake-indexeddb/auto";

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearQueuedUploads,
  countQueuedUploads,
  enqueueFiles,
  flushQueue,
  isIndexedDbAvailable,
  listQueuedUploads,
  recoverStalledUploads,
  removeQueuedUpload,
  resetFlushGuardForTests,
} from "@/lib/offline-queue";

function makeFile(
  name: string,
  contents = "image-bytes",
  lastModified = 1_700_000_000_000,
) {
  return new File([contents], name, { type: "image/jpeg", lastModified });
}

beforeEach(async () => {
  resetFlushGuardForTests();
  await clearQueuedUploads();
});

describe("environment", () => {
  it("reports IndexedDB as available under the test shim", () => {
    expect(isIndexedDbAvailable()).toBe(true);
  });
});

describe("enqueueFiles", () => {
  it("stages files and reports them back as metadata", async () => {
    const { added, skipped } = await enqueueFiles([
      makeFile("a.jpg"),
      makeFile("b.jpg"),
    ]);

    expect(added).toHaveLength(2);
    expect(skipped).toHaveLength(0);
    expect(await countQueuedUploads()).toBe(2);

    const items = await listQueuedUploads();
    expect(items.map((item) => item.name)).toEqual(["a.jpg", "b.jpg"]);
    expect(items[0]?.status).toBe("queued");
    expect(items[0]?.attempts).toBe(0);
  });

  it("does not stage the same file twice across separate drops", async () => {
    await enqueueFiles([makeFile("a.jpg")]);
    const second = await enqueueFiles([makeFile("a.jpg")]);

    expect(second.added).toHaveLength(0);
    expect(second.skipped).toHaveLength(1);
    expect(await countQueuedUploads()).toBe(1);
  });

  it("does not stage the same file twice within one drop", async () => {
    const { added, skipped } = await enqueueFiles([
      makeFile("a.jpg"),
      makeFile("a.jpg"),
    ]);

    expect(added).toHaveLength(1);
    expect(skipped).toHaveLength(1);
    expect(await countQueuedUploads()).toBe(1);
  });

  it("treats a same-named file with different bytes as a distinct file", async () => {
    await enqueueFiles([makeFile("a.jpg", "first", 1)]);
    const second = await enqueueFiles([makeFile("a.jpg", "second-longer", 2)]);

    expect(second.added).toHaveLength(1);
    expect(await countQueuedUploads()).toBe(2);
  });

  it("is a no-op for an empty selection", async () => {
    const result = await enqueueFiles([]);
    expect(result.added).toHaveLength(0);
    expect(await countQueuedUploads()).toBe(0);
  });

  it("omits the file bytes from the metadata it returns", async () => {
    const { added } = await enqueueFiles([makeFile("a.jpg")]);
    // The panel renders these straight into React state; carrying the bytes
    // would pin every staged file in memory.
    expect(added[0]).not.toHaveProperty("bytes");

    const [listed] = await listQueuedUploads();
    expect(listed).not.toHaveProperty("bytes");
  });
});

describe("removal", () => {
  it("removes a single queued file", async () => {
    const { added } = await enqueueFiles([
      makeFile("a.jpg"),
      makeFile("b.jpg"),
    ]);
    const target = added[0];
    if (!target) throw new Error("expected a queued file");

    await removeQueuedUpload(target.id);

    const remaining = await listQueuedUploads();
    expect(remaining.map((item) => item.name)).toEqual(["b.jpg"]);
  });

  it("clears the whole queue", async () => {
    await enqueueFiles([makeFile("a.jpg"), makeFile("b.jpg")]);
    await clearQueuedUploads();
    expect(await countQueuedUploads()).toBe(0);
  });
});

describe("flushQueue", () => {
  it("uploads every queued file and empties the queue", async () => {
    await enqueueFiles([makeFile("a.jpg"), makeFile("b.jpg")]);
    const uploader = vi.fn().mockResolvedValue({ results: [] });

    const result = await flushQueue(uploader);

    expect(result).toMatchObject({ uploaded: 2, failed: 0, skipped: false });
    expect(uploader).toHaveBeenCalledTimes(2);
    expect(await countQueuedUploads()).toBe(0);
  });

  it("hands the uploader a real File with the original name and type", async () => {
    await enqueueFiles([makeFile("holiday.jpg")]);
    const uploader = vi.fn().mockResolvedValue({ results: [] });

    await flushQueue(uploader);

    const [files] = uploader.mock.calls[0] ?? [];
    const file = (files as File[])[0];
    expect(file).toBeInstanceOf(File);
    expect(file?.name).toBe("holiday.jpg");
    expect(file?.type).toBe("image/jpeg");
    expect(await file?.text()).toBe("image-bytes");
  });

  it("keeps a failed file queued and counts the attempt", async () => {
    await enqueueFiles([makeFile("a.jpg")]);
    const uploader = vi.fn().mockRejectedValue(new Error("Network Error"));

    const result = await flushQueue(uploader);

    expect(result).toMatchObject({ uploaded: 0, failed: 1 });
    const [item] = await listQueuedUploads();
    // Back to `queued`, not stranded in `uploading` -- otherwise the next flush
    // would skip it forever.
    expect(item?.status).toBe("queued");
    expect(item?.attempts).toBe(1);
    expect(item?.lastError).toBe("Network Error");
  });

  it("removes the files that succeed even when others fail", async () => {
    await enqueueFiles([makeFile("good.jpg"), makeFile("bad.jpg")]);
    const uploader = vi.fn(async (files: File[]) => {
      if (files[0]?.name === "bad.jpg") throw new Error("rejected");
      return { results: [] };
    });

    const result = await flushQueue(uploader);

    expect(result).toMatchObject({ uploaded: 1, failed: 1 });
    const remaining = await listQueuedUploads();
    expect(remaining.map((item) => item.name)).toEqual(["bad.jpg"]);
  });

  it("does not submit the same file twice when two flushes overlap", async () => {
    await enqueueFiles([makeFile("a.jpg")]);

    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const uploader = vi.fn(async () => {
      await gate;
      return { results: [] };
    });

    // Two triggers land together -- the `online` event and a manual retry.
    const first = flushQueue(uploader);
    const second = flushQueue(uploader);
    release?.();
    const [firstResult, secondResult] = await Promise.all([first, second]);

    expect(uploader).toHaveBeenCalledTimes(1);
    expect(firstResult.uploaded).toBe(1);
    expect(secondResult.skipped).toBe(true);
    expect(await countQueuedUploads()).toBe(0);
  });

  it("is a no-op on an empty queue", async () => {
    const uploader = vi.fn();
    const result = await flushQueue(uploader);
    expect(uploader).not.toHaveBeenCalled();
    expect(result).toMatchObject({ uploaded: 0, failed: 0 });
  });
});

describe("recoverStalledUploads", () => {
  it("returns a file stranded in `uploading` to `queued`", async () => {
    await enqueueFiles([makeFile("a.jpg")]);

    // Simulate a tab closed mid-upload: the uploader never settles, so the
    // record is left marked `uploading`.
    const neverResolves = vi.fn(() => new Promise<never>(() => {}));
    void flushQueue(neverResolves);
    await vi.waitFor(async () => {
      const [item] = await listQueuedUploads();
      expect(item?.status).toBe("uploading");
    });

    resetFlushGuardForTests();
    const recovered = await recoverStalledUploads();

    expect(recovered).toBe(1);
    const [item] = await listQueuedUploads();
    expect(item?.status).toBe("queued");
  });

  it("leaves an ordinary queued file alone", async () => {
    await enqueueFiles([makeFile("a.jpg")]);
    expect(await recoverStalledUploads()).toBe(0);
  });
});

describe("secret containment", () => {
  it("stores nothing beyond the file bytes and display metadata", async () => {
    await enqueueFiles([makeFile("a.jpg")]);
    const [item] = await listQueuedUploads();
    if (!item) throw new Error("expected a queued file");

    // Auth is cookie-based and the vault key is memory-only (store/vaultStore).
    // Assert on the exact key set so adding a field to the record is a
    // deliberate decision that has to come through this test.
    expect(Object.keys(item).sort()).toEqual(
      [
        "attempts",
        "id",
        "lastModified",
        "name",
        "queuedAt",
        "seq",
        "size",
        "status",
        "type",
      ].sort(),
    );
  });

  it("does not leak a sentinel credential into the persisted record", async () => {
    const sentinel = "vault-master-key-do-not-persist";
    // A credential that happens to be in scope must not end up serialised into
    // the queue by a future change to enqueueFiles.
    await enqueueFiles([makeFile("a.jpg", sentinel)]);

    const items = await listQueuedUploads();
    expect(JSON.stringify(items)).not.toContain(sentinel);
  });
});
