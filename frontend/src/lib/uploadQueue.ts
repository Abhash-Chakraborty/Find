const DB_NAME = "find-upload-queue";
const STORE = "queue";
const DB_VERSION = 1;

export type QueueItemStatus = "draft" | "pending" | "failed";

export interface QueueItem {
  id: string;
  filename: string;
  blob: Blob;
  status: QueueItemStatus;
  addedAt: number;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE, { keyPath: "id" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function enqueue(file: File): Promise<QueueItem> {
  const db = await openDb();
  const item: QueueItem = {
    id: `${Date.now()}-${file.name}`,
    filename: file.name,
    blob: file,
    status: "draft",
    addedAt: Date.now(),
  };
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(item);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  return item;
}

export async function getQueue(): Promise<QueueItem[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result as QueueItem[]);
    req.onerror = () => reject(req.error);
  });
}

export async function updateStatus(id: string, status: QueueItemStatus): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    const req = store.get(id);
    req.onsuccess = () => {
      const item = req.result as QueueItem;
      if (item) store.put({ ...item, status });
      resolve();
    };
    req.onerror = () => reject(req.error);
  });
}

export async function dequeue(id: string): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
