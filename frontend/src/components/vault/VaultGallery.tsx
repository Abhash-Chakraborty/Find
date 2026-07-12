"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageOff, Loader2, Lock, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AssetViewer } from "@/components/asset-viewer";
import {
  TimelineMediaView,
  type TimelineMediaViewerRenderProps,
} from "@/components/timeline-media-view";
import { vaultStore } from "@/store/vaultStore";
import { VaultUnlock } from "./VaultUnlock";
import {
  fetchVaultOriginal,
  fetchVaultThumbnail,
  isExpiredVaultSession,
  listVaultItems,
  lockVaultSession,
  restoreVaultItem,
  type VaultListItem,
} from "./vault-client";

const VAULT_QUERY_KEY = ["vault-gallery"] as const;
const THUMBNAIL_CONCURRENCY = 3;

interface VaultViewerProps
  extends TimelineMediaViewerRenderProps<VaultListItem> {
  sessionToken: string;
  thumbnailUrls: Readonly<Record<number, string>>;
  onSessionExpired: () => void;
  onLoadError: () => void;
}

function VaultViewer({
  items,
  index,
  onIndexChange,
  onClose,
  sessionToken,
  thumbnailUrls,
  onSessionExpired,
  onLoadError,
}: VaultViewerProps) {
  const activeId = items[index]?.id;
  const [original, setOriginal] = useState<{
    mediaId: number;
    url: string;
  } | null>(null);
  const handlersRef = useRef({ onClose, onSessionExpired, onLoadError });

  useEffect(() => {
    handlersRef.current = { onClose, onSessionExpired, onLoadError };
  }, [onClose, onLoadError, onSessionExpired]);

  useEffect(() => {
    if (!activeId) {
      return;
    }

    let cancelled = false;
    let objectUrl: string | null = null;
    setOriginal(null);

    void fetchVaultOriginal(activeId, sessionToken)
      .then((blob) => {
        if (cancelled) {
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setOriginal({ mediaId: activeId, url: objectUrl });
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        if (isExpiredVaultSession(error)) {
          handlersRef.current.onClose();
          handlersRef.current.onSessionExpired();
          return;
        }
        handlersRef.current.onLoadError();
      });

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [activeId, sessionToken]);

  const assets = useMemo(
    () =>
      items.map((item) => {
        const thumbnailUrl = thumbnailUrls[item.id] ?? "";
        return {
          id: item.id,
          thumbnailUrl,
          originalUrl:
            original?.mediaId === item.id ? original.url : thumbnailUrl,
        };
      }),
    [items, original, thumbnailUrls],
  );

  return (
    <AssetViewer
      assets={assets}
      index={index}
      onIndexChange={onIndexChange}
      onClose={onClose}
    />
  );
}

export function VaultGallery() {
  const queryClient = useQueryClient();
  const isUnlocked = vaultStore((state) => state.isUnlocked);
  const sessionToken = vaultStore((state) => state.sessionToken);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [thumbnailUrls, setThumbnailUrls] = useState<Record<number, string>>(
    {},
  );
  const objectUrlsRef = useRef<Record<number, string>>({});

  const revokeThumbnails = useCallback(() => {
    for (const url of Object.values(objectUrlsRef.current)) {
      URL.revokeObjectURL(url);
    }
    objectUrlsRef.current = {};
    setThumbnailUrls({});
  }, []);

  const clearSession = useCallback(
    (message: string) => {
      revokeThumbnails();
      queryClient.removeQueries({ queryKey: VAULT_QUERY_KEY });
      vaultStore.getState().lock();
      setSessionMessage(message);
    },
    [queryClient, revokeThumbnails],
  );

  const listQuery = useQuery<VaultListItem[], Error>({
    queryKey: VAULT_QUERY_KEY,
    enabled: isUnlocked && !!sessionToken,
    queryFn: () => listVaultItems(sessionToken ?? ""),
  });

  useEffect(() => {
    if (!listQuery.error) {
      return;
    }

    if (isExpiredVaultSession(listQuery.error)) {
      clearSession("Session expired. Please unlock again.");
    }
  }, [clearSession, listQuery.error]);

  useEffect(() => {
    if (!isUnlocked) {
      revokeThumbnails();
      return;
    }
    setSessionMessage(null);
  }, [isUnlocked, revokeThumbnails]);

  useEffect(() => {
    const items = listQuery.data;
    if (!isUnlocked || !sessionToken || !items) {
      return;
    }

    const currentIds = new Set(items.map((item) => item.id));
    for (const [rawId, url] of Object.entries(objectUrlsRef.current)) {
      const mediaId = Number(rawId);
      if (!currentIds.has(mediaId)) {
        URL.revokeObjectURL(url);
        delete objectUrlsRef.current[mediaId];
      }
    }
    setThumbnailUrls({ ...objectUrlsRef.current });

    const queue = items.filter((item) => !objectUrlsRef.current[item.id]);
    let cursor = 0;
    let cancelled = false;

    const worker = async () => {
      while (!cancelled) {
        const item = queue[cursor];
        cursor += 1;
        if (!item) {
          return;
        }

        try {
          const blob = await fetchVaultThumbnail(item.id, sessionToken);
          if (cancelled) {
            return;
          }
          const url = URL.createObjectURL(blob);
          objectUrlsRef.current[item.id] = url;
          setThumbnailUrls((current) => ({ ...current, [item.id]: url }));
        } catch (error) {
          if (cancelled) {
            return;
          }
          if (isExpiredVaultSession(error)) {
            cancelled = true;
            clearSession("Session expired. Please unlock again.");
            return;
          }
          setSessionMessage(
            "Some encrypted previews could not be loaded. You can retry shortly.",
          );
        }
      }
    };

    const workers = Array.from(
      { length: Math.min(THUMBNAIL_CONCURRENCY, queue.length) },
      () => worker(),
    );
    void Promise.all(workers);

    return () => {
      cancelled = true;
    };
  }, [clearSession, isUnlocked, listQuery.data, sessionToken]);

  useEffect(() => revokeThumbnails, [revokeThumbnails]);

  const restoreMutation = useMutation({
    mutationFn: async (mediaId: number) => {
      if (!sessionToken) {
        throw new Error("Vault session missing");
      }
      await restoreVaultItem(mediaId, sessionToken);
      return mediaId;
    },
    onSuccess: async (mediaId) => {
      const thumbnailUrl = objectUrlsRef.current[mediaId];
      if (thumbnailUrl) {
        URL.revokeObjectURL(thumbnailUrl);
        delete objectUrlsRef.current[mediaId];
        setThumbnailUrls({ ...objectUrlsRef.current });
      }
      setSessionMessage("Image restored to your timeline.");
      await queryClient.invalidateQueries({ queryKey: VAULT_QUERY_KEY });
    },
    onError: (error) => {
      if (isExpiredVaultSession(error)) {
        clearSession("Session expired. Please unlock again.");
        return;
      }
      setSessionMessage(
        "The image could not be restored. Its encrypted copy is still safe.",
      );
    },
  });

  const handleLock = useCallback(() => {
    const token = sessionToken;
    revokeThumbnails();
    queryClient.removeQueries({ queryKey: VAULT_QUERY_KEY });
    vaultStore.getState().lock();
    setSessionMessage(null);

    if (token) {
      void lockVaultSession(token).catch((error: unknown) => {
        if (!isExpiredVaultSession(error)) {
          setSessionMessage(
            "Vault locked here. The server session will expire automatically.",
          );
        }
      });
    }
  }, [queryClient, revokeThumbnails, sessionToken]);

  const handleViewerError = useCallback(() => {
    setSessionMessage(
      "The full encrypted image could not be opened. Its preview remains available.",
    );
  }, []);
  const handleSessionExpired = useCallback(() => {
    clearSession("Session expired. Please unlock again.");
  }, [clearSession]);

  if (!isUnlocked || !sessionToken) {
    return (
      <div className="page-shell">
        <div className="container-shell py-10 md:py-14">
          {sessionMessage && (
            <p className="mx-auto mb-4 max-w-md text-center text-sm text-[#ff9bab]">
              {sessionMessage}
            </p>
          )}
          <VaultUnlock />
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <div className="container-shell py-8 md:py-12">
        <div className="frost-panel delayed-enter mb-8 flex flex-col justify-between gap-4 rounded-3xl px-5 py-4 md:flex-row md:items-center">
          <div>
            <h1 className="text-lg font-semibold text-[color:var(--near-white)]">
              Locked Vault
            </h1>
            <p className="mt-1 text-xs text-[color:var(--silver)]">
              Originals stay encrypted at rest. This session exists in memory
              only.
            </p>
          </div>

          <button
            type="button"
            onClick={handleLock}
            className="inline-flex items-center justify-center gap-2 rounded-full border border-[var(--frost)] px-4 py-2 text-xs font-medium text-[color:var(--silver)] transition-colors hover:bg-[color:var(--frost-soft)] hover:text-[color:var(--near-white)]"
          >
            <Lock className="h-4 w-4" />
            Lock Vault
          </button>
        </div>

        {sessionMessage && (
          <p className="mb-6 text-sm text-[color:var(--silver)]">
            {sessionMessage}
          </p>
        )}

        {listQuery.isLoading && (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="h-8 w-8 animate-spin text-[color:var(--silver)]" />
          </div>
        )}

        {listQuery.isError && !isExpiredVaultSession(listQuery.error) && (
          <div className="py-32 text-center">
            <p className="text-[color:var(--silver)]">Failed to load vault</p>
          </div>
        )}

        {listQuery.data && (
          <TimelineMediaView
            items={listQuery.data}
            getId={(item) => item.id}
            getDate={(item) => item.created_at}
            getWidth={(item) => item.width}
            getHeight={(item) => item.height}
            getThumbnailUrl={(item) => thumbnailUrls[item.id]}
            getOriginalUrl={(item) => thumbnailUrls[item.id]}
            getAlt={(item) => item.filename}
            getItemTestId={(item) => `vault-item-${item.id}`}
            getOpenTestId={(item) => `open-vault-item-${item.id}`}
            controlsId="vault-media-timeline"
            empty={
              <div className="frost-panel mx-auto rounded-3xl px-8 py-16 text-center">
                <ImageOff className="mx-auto mb-4 h-12 w-12 text-[color:var(--muted)]" />
                <p className="mb-2 text-[color:var(--near-white)]">
                  No locked images yet
                </p>
                <p className="text-sm text-[color:var(--silver)]">
                  Unlock the vault from Gallery to move images here.
                </p>
              </div>
            }
            renderItemActions={(item) => (
              <button
                type="button"
                aria-label={`Restore ${item.filename}`}
                disabled={
                  restoreMutation.isPending &&
                  restoreMutation.variables === item.id
                }
                onClick={() => restoreMutation.mutate(item.id)}
                className="inline-flex items-center gap-1 rounded-full bg-black/65 px-3 py-1.5 text-xs font-medium text-white backdrop-blur transition hover:bg-black/85 disabled:cursor-wait disabled:opacity-60"
              >
                {restoreMutation.isPending &&
                restoreMutation.variables === item.id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RotateCcw className="h-3.5 w-3.5" />
                )}
                Restore
              </button>
            )}
            renderViewer={(props) => (
              <VaultViewer
                {...props}
                sessionToken={sessionToken}
                thumbnailUrls={thumbnailUrls}
                onSessionExpired={handleSessionExpired}
                onLoadError={handleViewerError}
              />
            )}
          />
        )}
      </div>
    </div>
  );
}
