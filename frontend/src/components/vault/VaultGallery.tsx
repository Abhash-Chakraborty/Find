"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ImageOff,
  KeyRound,
  Loader2,
  Lock,
  RotateCcw,
  Settings2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AssetViewer } from "@/components/asset-viewer";
import {
  TimelineMediaView,
  type TimelineMediaViewerRenderProps,
} from "@/components/timeline-media-view";
import { vaultStore } from "@/store/vaultStore";
import { VaultUnlock } from "./VaultUnlock";
import {
  changeVaultPassword,
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
  const [pendingRestoreIds, setPendingRestoreIds] = useState<Set<number>>(
    () => new Set(),
  );
  const [lockMode, setLockMode] = useState<"immediate" | "delay" | "idle">(
    () => {
      try {
        const saved = localStorage.getItem("find-vault-lock-mode");
        return saved === "delay" || saved === "idle" ? saved : "immediate";
      } catch {
        return "immediate";
      }
    },
  );
  const [lockDelay, setLockDelay] = useState(() => {
    try {
      return Number(localStorage.getItem("find-vault-lock-delay")) || 5;
    } catch {
      return 5;
    }
  });
  const [newRecoveryCode, setNewRecoveryCode] = useState<string | null>(null);
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
            "Some private previews could not be loaded. You can retry shortly.",
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
      setPendingRestoreIds((current) => new Set(current).add(mediaId));
      await restoreVaultItem(mediaId, sessionToken);
      return mediaId;
    },
    onSuccess: async (mediaId) => {
      setPendingRestoreIds((current) => {
        const next = new Set(current);
        next.delete(mediaId);
        return next;
      });
      const thumbnailUrl = objectUrlsRef.current[mediaId];
      if (thumbnailUrl) {
        URL.revokeObjectURL(thumbnailUrl);
        delete objectUrlsRef.current[mediaId];
        setThumbnailUrls({ ...objectUrlsRef.current });
      }
      setSessionMessage("Image restored to your timeline.");
      await queryClient.invalidateQueries({ queryKey: VAULT_QUERY_KEY });
    },
    onError: (error, mediaId) => {
      setPendingRestoreIds((current) => {
        const next = new Set(current);
        next.delete(mediaId);
        return next;
      });
      if (isExpiredVaultSession(error)) {
        clearSession("Session expired. Please unlock again.");
        return;
      }
      setSessionMessage(
        "The image could not be restored. Its private vault copy is unchanged.",
      );
    },
  });

  const passwordMutation = useMutation({
    mutationFn: ({ current, next }: { current: string; next: string }) =>
      changeVaultPassword(current, next),
    onSuccess: ({ session_token, recovery_code }) => {
      vaultStore.getState().unlock(session_token);
      setNewRecoveryCode(recovery_code);
      setSessionMessage(
        "Vault password updated. Save the new recovery code below.",
      );
    },
    onError: () =>
      setSessionMessage(
        "Vault password could not be changed. Check the current password.",
      ),
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

  useEffect(() => {
    if (!isUnlocked) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const lockAfter = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(handleLock, lockDelay * 60_000);
    };
    const visibility = () => {
      if (document.hidden) {
        if (lockMode === "immediate") handleLock();
        else if (lockMode === "delay") lockAfter();
      } else if (timer && lockMode === "delay") {
        clearTimeout(timer);
      }
    };
    const activity = () => {
      if (lockMode === "idle") lockAfter();
    };
    document.addEventListener("visibilitychange", visibility);
    if (lockMode === "idle") {
      for (const event of ["pointerdown", "keydown", "scroll"] as const)
        window.addEventListener(event, activity, { passive: true });
      lockAfter();
    }
    return () => {
      document.removeEventListener("visibilitychange", visibility);
      for (const event of ["pointerdown", "keydown", "scroll"] as const)
        window.removeEventListener(event, activity);
      if (timer) clearTimeout(timer);
    };
  }, [handleLock, isUnlocked, lockDelay, lockMode]);

  const handleViewerError = useCallback(() => {
    setSessionMessage(
      "The full private image could not be opened. Its preview remains available.",
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
              Photos remain in private storage behind this local lock. The
              session token exists in memory only.
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

        <details className="mb-8 rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-4">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold">
            <Settings2 className="h-4 w-4" />
            Vault security
          </summary>
          <div className="mt-4 grid gap-5 lg:grid-cols-2">
            <fieldset>
              <legend className="text-sm font-medium">Automatic lock</legend>
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                {(["immediate", "delay", "idle"] as const).map((mode) => (
                  <label
                    key={mode}
                    className={`cursor-pointer rounded-xl border px-3 py-2 text-center text-xs capitalize ${lockMode === mode ? "border-[color:var(--near-white)] bg-[color:var(--surface-hover)]" : "border-[color:var(--frost)] text-[color:var(--silver)]"}`}
                  >
                    <input
                      className="sr-only"
                      type="radio"
                      name="vault-lock-mode"
                      checked={lockMode === mode}
                      onChange={() => {
                        setLockMode(mode);
                        localStorage.setItem("find-vault-lock-mode", mode);
                      }}
                    />
                    {mode === "idle" ? "When idle" : mode}
                  </label>
                ))}
              </div>
              <label className="mt-3 block text-xs text-[color:var(--silver)]">
                Delay / idle timeout{" "}
                <select
                  value={lockDelay}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    setLockDelay(value);
                    localStorage.setItem(
                      "find-vault-lock-delay",
                      String(value),
                    );
                  }}
                  className="ml-2 rounded-lg border border-[var(--frost)] bg-[color:var(--void)] px-2 py-1"
                >
                  <option value={1}>1 minute</option>
                  <option value={5}>5 minutes</option>
                  <option value={15}>15 minutes</option>
                  <option value={30}>30 minutes</option>
                </select>
              </label>
            </fieldset>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                const current = String(data.get("current") ?? "");
                const next = String(data.get("next") ?? "");
                const confirmation = String(data.get("confirmation") ?? "");
                if (next !== confirmation) {
                  setSessionMessage("New vault passwords do not match.");
                  return;
                }
                passwordMutation.mutate({ current, next });
              }}
            >
              <p className="text-sm font-medium">Change password</p>
              <div className="mt-2 grid gap-2">
                <input
                  name="current"
                  required
                  type="password"
                  autoComplete="current-password"
                  placeholder="Current password"
                  className="rounded-lg border border-[var(--frost)] bg-[color:var(--void)] px-3 py-2 text-sm"
                />
                <input
                  name="next"
                  required
                  minLength={8}
                  type="password"
                  autoComplete="new-password"
                  placeholder="New password"
                  className="rounded-lg border border-[var(--frost)] bg-[color:var(--void)] px-3 py-2 text-sm"
                />
                <input
                  name="confirmation"
                  required
                  minLength={8}
                  type="password"
                  autoComplete="new-password"
                  placeholder="Confirm new password"
                  className="rounded-lg border border-[var(--frost)] bg-[color:var(--void)] px-3 py-2 text-sm"
                />
                <button
                  type="submit"
                  disabled={passwordMutation.isPending}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-[color:var(--near-white)] px-3 py-2 text-sm font-semibold text-[color:var(--void)]"
                >
                  <KeyRound className="h-4 w-4" />
                  Update password
                </button>
              </div>
            </form>
          </div>
          {newRecoveryCode && (
            <div className="mt-4 rounded-xl border border-[var(--frost)] p-3">
              <p className="text-xs text-[color:var(--silver)]">
                New one-time recovery code
              </p>
              <code className="mt-1 block select-all text-sm tracking-wider">
                {newRecoveryCode}
              </code>
            </div>
          )}
        </details>

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
                disabled={pendingRestoreIds.has(item.id)}
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
