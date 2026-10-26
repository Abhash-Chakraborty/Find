"use client";

import { CloudOff, RefreshCw, Trash2, WifiOff } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { uploadImages } from "@/lib/api";
import {
  clearQueuedUploads,
  countQueuedUploads,
  flushQueue,
  isIndexedDbAvailable,
  listQueuedUploads,
  type QueuedUpload,
  recoverStalledUploads,
  removeQueuedUpload,
} from "@/lib/offline-queue";
import { useOnlineStatus } from "@/lib/use-online-status";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Queue state plus the actions the upload page needs.
 *
 * Kept as a hook so the page can stage files into the queue without rendering
 * the panel, and the panel can render without owning the staging decision.
 */
export function useOfflineUploadQueue() {
  const online = useOnlineStatus();
  const [items, setItems] = useState<QueuedUpload[]>([]);
  const [flushing, setFlushing] = useState(false);
  const available = isIndexedDbAvailable();

  const refresh = useCallback(async () => {
    if (!available) return;
    try {
      setItems(await listQueuedUploads());
    } catch (error) {
      console.warn("Could not read the offline upload queue", error);
    }
  }, [available]);

  const flush = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!available) return;
      if ((await countQueuedUploads()) === 0) return;

      setFlushing(true);
      try {
        const result = await flushQueue((files) => uploadImages(files));
        // `skipped` means another trigger was already flushing; reporting it
        // would double-toast a single run.
        if (!result.skipped && !options?.silent) {
          if (result.uploaded > 0) {
            toast.success(
              `Uploaded ${result.uploaded} queued file${result.uploaded === 1 ? "" : "s"}`,
            );
          }
          if (result.failed > 0) {
            toast.error(
              `${result.failed} queued file${result.failed === 1 ? "" : "s"} still pending`,
            );
          }
        }
      } catch (error) {
        console.warn("Offline queue flush failed", error);
      } finally {
        setFlushing(false);
        await refresh();
      }
    },
    [available, refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      await removeQueuedUpload(id);
      await refresh();
    },
    [refresh],
  );

  const clear = useCallback(async () => {
    await clearQueuedUploads();
    await refresh();
  }, [refresh]);

  // On mount: recover anything a closed tab left mid-flight, then show it.
  useEffect(() => {
    if (!available) return;
    void recoverStalledUploads()
      .catch(() => 0)
      .then(() => refresh());
  }, [available, refresh]);

  // Connectivity returned -- send whatever is staged. Silent: the user did not
  // ask for this, so it should not interrupt them unless something fails.
  useEffect(() => {
    if (!available || !online) return;
    void flush({ silent: false });
  }, [available, online, flush]);

  return { items, online, flushing, available, refresh, flush, remove, clear };
}

type OfflineUploadQueueProps = ReturnType<typeof useOfflineUploadQueue>;

/**
 * Panel listing files staged for upload while the backend was unreachable.
 *
 * Renders nothing when the queue is empty and the connection is fine, so the
 * normal online path is visually unchanged (issue #259: "Existing desktop web
 * behavior remains unchanged").
 */
export function OfflineUploadQueue({
  items,
  online,
  flushing,
  available,
  flush,
  remove,
  clear,
}: OfflineUploadQueueProps) {
  if (!available) {
    return null;
  }
  if (items.length === 0 && online) {
    return null;
  }

  return (
    <section
      aria-labelledby="offline-queue-heading"
      className="mb-5 rounded-xl border border-[var(--frost)] bg-[color:var(--frost-soft)] p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {online ? (
            <CloudOff
              className="h-4 w-4 text-[color:var(--yellow)]"
              aria-hidden
            />
          ) : (
            <WifiOff
              className="h-4 w-4 text-[color:var(--yellow)]"
              aria-hidden
            />
          )}
          <h2
            id="offline-queue-heading"
            className="text-sm font-semibold text-[color:var(--near-white)]"
          >
            {online ? "Waiting to upload" : "Offline"}
          </h2>
          {items.length > 0 && (
            <span className="accent-badge status-pending">
              {items.length} file{items.length === 1 ? "" : "s"}
            </span>
          )}
        </div>

        {items.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void flush()}
              disabled={!online || flushing}
              className="icon-button disabled:cursor-not-allowed disabled:opacity-50"
              aria-label="Retry queued uploads now"
              title={
                online ? "Retry queued uploads now" : "Waiting for a connection"
              }
            >
              <RefreshCw
                className={`h-4 w-4 ${flushing ? "animate-spin" : ""}`}
                aria-hidden
              />
            </button>
            <button
              type="button"
              onClick={() => void clear()}
              className="icon-button"
              aria-label="Remove all queued files"
              title="Remove all queued files"
            >
              <Trash2 className="h-4 w-4" aria-hidden />
            </button>
          </div>
        )}
      </div>

      <p className="mt-2 text-xs leading-relaxed text-[color:var(--muted)]">
        {online
          ? "These files are staged on this device and are being submitted now."
          : "Files you add are staged on this device and will be submitted automatically when the connection returns. Nothing has been sent yet."}
      </p>

      {items.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-[var(--frost)] px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm text-[color:var(--near-white)]">
                  {item.name}
                </p>
                <p className="text-xs text-[color:var(--muted)]">
                  {formatSize(item.size)}
                  {item.attempts > 0 && (
                    <>
                      {" · "}
                      {item.attempts} failed attempt
                      {item.attempts === 1 ? "" : "s"}
                    </>
                  )}
                  {item.lastError && <> · {item.lastError}</>}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void remove(item.id)}
                className="icon-button shrink-0"
                aria-label={`Remove ${item.name} from the upload queue`}
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
