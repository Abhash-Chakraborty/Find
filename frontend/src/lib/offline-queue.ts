/**
 * IndexedDB-backed queue for uploads staged while the backend is unreachable.
 *
 * Why IndexedDB rather than the existing zustand `uploadQueueStore`: that store
 * persists to localStorage, which is synchronous, string-only, and capped at a
 * few megabytes. This queue holds the file bytes themselves, so it needs a
 * store that takes binary data and does not block the main thread.
 *
 * What this deliberately does NOT hold: anything secret. Only the file bytes the
 * user chose plus the metadata needed to display and re-submit them. Auth is
 * cookie-based and the vault key is memory-only (see store/vaultStore.ts) --
 * neither may ever be written here.
 */

const DB_NAME = "find-offline-uploads";
const DB_VERSION = 1;
const STORE_NAME = "queued-uploads";

/**
 * `uploading` is persisted rather than kept in memory so a tab closed
 * mid-flight leaves a recoverable marker instead of an item that looks queued
 * and gets sent twice.
 */
export type QueuedUploadStatus = "queued" | "uploading";

/** Metadata for one staged file. The bytes live in {@link QueuedUploadRecord}. */
export interface QueuedUpload {
  id: string;
  name: string;
  size: number;
  type: string;
  lastModified: number;
  queuedAt: number;
  /**
   * Insertion order.
   *
   * `queuedAt` alone is not enough: a multi-file drop stages every file inside
   * the same millisecond, so sorting on it leaves the panel order and the
   * upload order arbitrary.
   */
  seq: number;
  attempts: number;
  status: QueuedUploadStatus;
  lastError?: string;
}

/**
 * A staged file including its bytes.
 *
 * Bytes are held as an ArrayBuffer rather than the original Blob. IndexedDB
 * accepts Blobs in principle, but they survive a structured clone far less
 * reliably across engines than a buffer does, and the File is reconstructed on
 * the way out anyway.
 */
export interface QueuedUploadRecord extends QueuedUpload {
  bytes: ArrayBuffer;
}

export interface EnqueueResult {
  added: QueuedUpload[];
  /** Files already present in the queue, matched on name + size + mtime. */
  skipped: File[];
}

export interface FlushResult {
  uploaded: number;
  failed: number;
  /** True when a flush was already running and this call did nothing. */
  skipped: boolean;
}

/** Uploader injected by the caller so this module never imports the API client. */
export type QueueUploader = (files: File[]) => Promise<unknown>;

export function isIndexedDbAvailable(): boolean {
  return typeof globalThis !== "undefined" && "indexedDB" in globalThis;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!isIndexedDbAvailable()) {
      reject(new Error("IndexedDB is not available in this environment"));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: "id" });
        store.createIndex("dedupeKey", "dedupeKey", { unique: false });
        store.createIndex("seq", "seq", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function runTransaction<T>(
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore) => IDBRequest<T> | void,
): Promise<T | undefined> {
  return openDb().then(
    (db) =>
      new Promise<T | undefined>((resolve, reject) => {
        const transaction = db.transaction(STORE_NAME, mode);
        const store = transaction.objectStore(STORE_NAME);
        let result: T | undefined;
        const request = work(store);
        if (request) {
          request.onsuccess = () => {
            result = request.result;
          };
        }
        transaction.oncomplete = () => {
          db.close();
          resolve(result);
        };
        transaction.onerror = () => {
          db.close();
          reject(transaction.error);
        };
        transaction.onabort = () => {
          db.close();
          reject(transaction.error);
        };
      }),
  );
}

/**
 * Identity for dedupe. Content hashing would be stricter, but hashing a whole
 * camera roll on the main thread to answer "did they pick this twice?" costs
 * far more than it saves -- and the backend hashes on receipt anyway, so an
 * escapee is still caught server-side and returned as `duplicate`.
 */
function dedupeKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function toMetadata(
  record: QueuedUploadRecord & { dedupeKey?: string },
): QueuedUpload {
  const { bytes: _bytes, dedupeKey: _key, ...metadata } = record;
  return metadata;
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `queued-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Stage files for later upload, skipping ones already queued. */
export async function enqueueFiles(files: File[]): Promise<EnqueueResult> {
  if (files.length === 0) {
    return { added: [], skipped: [] };
  }

  const records = await listRecords();
  const existing = new Set(records.map((record) => record.dedupeKey));
  let nextSeq =
    records.reduce((max, record) => Math.max(max, record.seq), 0) + 1;

  const added: QueuedUpload[] = [];
  const skipped: File[] = [];
  const pending: Array<QueuedUploadRecord & { dedupeKey: string }> = [];

  for (const file of files) {
    const key = dedupeKey(file);
    // Check `existing` and this batch, so selecting the same file twice in one
    // drop does not create two records.
    if (existing.has(key) || pending.some((item) => item.dedupeKey === key)) {
      skipped.push(file);
      continue;
    }
    pending.push({
      id: newId(),
      name: file.name,
      size: file.size,
      type: file.type,
      lastModified: file.lastModified,
      queuedAt: Date.now(),
      seq: nextSeq++,
      attempts: 0,
      status: "queued",
      dedupeKey: key,
      bytes: await file.arrayBuffer(),
    });
  }

  if (pending.length > 0) {
    await runTransaction("readwrite", (store) => {
      for (const record of pending) {
        store.put(record);
      }
    });
    added.push(...pending.map(toMetadata));
  }

  return { added, skipped };
}

async function listRecords(): Promise<
  Array<QueuedUploadRecord & { dedupeKey: string }>
> {
  const records = await runTransaction<
    Array<QueuedUploadRecord & { dedupeKey: string }>
  >(
    "readonly",
    (store) =>
      store.getAll() as IDBRequest<
        Array<QueuedUploadRecord & { dedupeKey: string }>
      >,
  );
  return (records ?? []).sort((a, b) => a.seq - b.seq);
}

/**
 * Queue contents for display, oldest first.
 *
 * Bytes are stripped: the panel renders names and sizes, and holding every
 * staged file's bytes in React state would pin the whole queue in memory for
 * no benefit.
 */
export async function listQueuedUploads(): Promise<QueuedUpload[]> {
  const records = await listRecords();
  return records.map(toMetadata);
}

export async function countQueuedUploads(): Promise<number> {
  const count = await runTransaction<number>("readonly", (store) =>
    store.count(),
  );
  return count ?? 0;
}

export async function removeQueuedUpload(id: string): Promise<void> {
  await runTransaction("readwrite", (store) => {
    store.delete(id);
  });
}

export async function clearQueuedUploads(): Promise<void> {
  await runTransaction("readwrite", (store) => {
    store.clear();
  });
}

/**
 * Reset any record left in `uploading` back to `queued`.
 *
 * Called on start-up. A tab closed mid-upload leaves a stranded marker that
 * {@link flushQueue} would otherwise skip forever, so the item would sit in the
 * panel looking active and never send.
 */
export async function recoverStalledUploads(): Promise<number> {
  const records = await listRecords();
  const stalled = records.filter((record) => record.status === "uploading");
  if (stalled.length === 0) {
    return 0;
  }
  await runTransaction("readwrite", (store) => {
    for (const record of stalled) {
      store.put({ ...record, status: "queued" as const });
    }
  });
  return stalled.length;
}

// Single-flight guard. The flush can be triggered by the `online` event, by a
// manual retry, and by the upload page mounting -- all three can land at once,
// and without this each would send the same file.
let flushInFlight: Promise<FlushResult> | null = null;

/**
 * Upload everything staged, oldest first.
 *
 * An item is marked `uploading` before its request and deleted only after the
 * upload resolves, so an interrupted flush never loses a file and never sends
 * one twice. Failures stay queued with an incremented attempt count.
 */
export function flushQueue(uploader: QueueUploader): Promise<FlushResult> {
  if (flushInFlight) {
    return flushInFlight.then((result) => ({ ...result, skipped: true }));
  }
  flushInFlight = runFlush(uploader).finally(() => {
    flushInFlight = null;
  });
  return flushInFlight;
}

async function runFlush(uploader: QueueUploader): Promise<FlushResult> {
  const records = await listRecords();
  const pending = records.filter((record) => record.status === "queued");
  let uploaded = 0;
  let failed = 0;

  for (const record of pending) {
    await runTransaction("readwrite", (store) => {
      store.put({ ...record, status: "uploading" as const });
    });

    try {
      const file = new File([record.bytes], record.name, {
        type: record.type,
        lastModified: record.lastModified,
      });
      await uploader([file]);
      await removeQueuedUpload(record.id);
      uploaded += 1;
    } catch (error) {
      failed += 1;
      await runTransaction("readwrite", (store) => {
        store.put({
          ...record,
          status: "queued" as const,
          attempts: record.attempts + 1,
          lastError: error instanceof Error ? error.message : "Upload failed",
        });
      });
    }
  }

  return { uploaded, failed, skipped: false };
}

/** Test-only: drop the single-flight guard between cases. */
export function resetFlushGuardForTests(): void {
  flushInFlight = null;
}
