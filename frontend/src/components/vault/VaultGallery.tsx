"use client";

import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { ImageOff, Loader2, Lock } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { vaultStore } from "@/store/vaultStore";
import { VaultUnlock } from "./VaultUnlock";

type VaultListItem = {
  id: number;
  filename: string;
  content_type: string | null;
  created_at: string | null;
};

export function VaultGallery() {
  const isUnlocked = vaultStore((state) => state.isUnlocked);
  const sessionToken = vaultStore((state) => state.sessionToken);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [streamUrls, setStreamUrls] = useState<Record<number, string>>({});
  const objectUrlsRef = useRef<Record<number, string>>({});

  const listQuery = useQuery<VaultListItem[], Error>({
    queryKey: ["vault-gallery", sessionToken],
    enabled: isUnlocked && !!sessionToken,
    queryFn: async () => {
      const response = await api.get<VaultListItem[]>("/api/vault/list", {
        headers: {
          Authorization: `Bearer ${sessionToken}`,
        },
      });
      return response.data;
    },
  });

  useEffect(() => {
    if (!listQuery.error || !axios.isAxiosError(listQuery.error)) {
      return;
    }

    if (listQuery.error.response?.status === 401) {
      vaultStore.getState().lock();
      setSessionMessage("Session expired. Please unlock again.");
    }
  }, [listQuery.error]);

  useEffect(() => {
    if (!isUnlocked) {
      Object.values(objectUrlsRef.current).forEach((url) => {
        URL.revokeObjectURL(url);
      });
      objectUrlsRef.current = {};
      setStreamUrls({});
      return;
    }

    setSessionMessage(null);
  }, [isUnlocked]);

  useEffect(() => {
    if (!isUnlocked || !sessionToken || !listQuery.data) {
      return;
    }

    let cancelled = false;

    const loadStreams = async () => {
      const nextUrls: Record<number, string> = {};

      try {
        await Promise.all(
          listQuery.data.map(async (item) => {
            const response = await api.get<Blob>(
              `/api/vault/stream/${item.id}`,
              {
                headers: {
                  Authorization: `Bearer ${sessionToken}`,
                },
                responseType: "blob",
              },
            );

            if (!cancelled) {
              nextUrls[item.id] = URL.createObjectURL(response.data);
            }
          }),
        );

        if (cancelled) {
          Object.values(nextUrls).forEach((url) => {
            URL.revokeObjectURL(url);
          });
          return;
        }

        Object.values(objectUrlsRef.current).forEach((url) => {
          URL.revokeObjectURL(url);
        });
        objectUrlsRef.current = nextUrls;
        setStreamUrls(nextUrls);
      } catch (error) {
        Object.values(nextUrls).forEach((url) => {
          URL.revokeObjectURL(url);
        });

        if (axios.isAxiosError(error) && error.response?.status === 401) {
          vaultStore.getState().lock();
          setSessionMessage("Session expired. Please unlock again.");
        } else {
          setSessionMessage(
            "Some images could not be decrypted. Please try again.",
          );
        }
      }
    };

    void loadStreams();

    return () => {
      cancelled = true;
    };
  }, [isUnlocked, listQuery.data, sessionToken]);

  useEffect(() => {
    return () => {
      Object.values(objectUrlsRef.current).forEach((url) => {
        URL.revokeObjectURL(url);
      });
      objectUrlsRef.current = {};
    };
  }, []);

  if (!isUnlocked) {
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
      <div className="container-shell py-10 md:py-14">
        <div className="frost-panel delayed-enter mb-8 flex flex-col items-center justify-between gap-4 rounded-3xl px-4 py-3 md:flex-row">
          <div>
            <p className="text-sm font-medium text-[color:var(--near-white)]">
              Hidden Vault
            </p>
            <p className="text-xs text-[color:var(--silver)]">
              Encrypted images unlocked for this session only.
            </p>
          </div>

          <button
            type="button"
            onClick={() => vaultStore.getState().lock()}
            className="inline-flex items-center gap-2 rounded-full border border-[var(--frost)] px-4 py-2 text-xs font-medium text-[color:var(--silver)] transition-colors hover:bg-[color:var(--frost-soft)] hover:text-[color:var(--near-white)]"
          >
            <Lock className="h-4 w-4" />
            Lock Vault
          </button>
        </div>

        {sessionMessage && (
          <p className="mb-6 text-sm text-[#ff9bab]">{sessionMessage}</p>
        )}

        {listQuery.isLoading && (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="h-8 w-8 animate-spin text-[color:var(--silver)]" />
          </div>
        )}

        {listQuery.isError && !sessionMessage && (
          <div className="py-32 text-center">
            <p className="text-[color:var(--silver)]">Failed to load vault</p>
          </div>
        )}

        {listQuery.data && listQuery.data.length === 0 && (
          <div className="w-full">
            <div className="frost-panel mx-auto rounded-3xl px-8 py-16 text-center">
              <ImageOff className="mx-auto mb-4 h-12 w-12 text-[color:var(--muted)]" />
              <p className="mb-2 text-[color:var(--near-white)]">
                No hidden images yet
              </p>
            </div>
          </div>
        )}

        {listQuery.data && listQuery.data.length > 0 && (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">
            {listQuery.data.map((item) => {
              const imageSrc = streamUrls[item.id];

              return (
                <article
                  key={item.id}
                  className="frost-panel card-hover group relative overflow-hidden rounded-2xl"
                >
                  <div className="relative aspect-square w-full overflow-hidden bg-[color:var(--surface-soft)]">
                    {imageSrc ? (
                      // biome-ignore lint/performance/noImgElement: Vault previews use authenticated blob URLs from decrypted local streams, not public image URLs.
                      <img
                        src={imageSrc}
                        alt={item.filename}
                        className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.035]"
                      />
                    ) : (
                      <div
                        className="flex h-full w-full flex-col items-center justify-center gap-2 text-[color:var(--muted)]"
                        role="img"
                        aria-label="Vault preview unavailable"
                      >
                        <Loader2 className="h-7 w-7 animate-spin" />
                        <span className="text-xs">Decrypting</span>
                      </div>
                    )}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/12 to-transparent opacity-60 transition-opacity group-hover:opacity-90" />
                  </div>

                  <div className="space-y-1 p-3">
                    <p className="truncate text-xs font-medium text-[color:var(--near-white)]">
                      {item.filename}
                    </p>
                    <p className="text-[11px] text-[color:var(--silver)]">
                      {item.created_at
                        ? new Date(item.created_at).toLocaleString()
                        : "Unknown date"}
                    </p>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
