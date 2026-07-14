"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Plus, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  addAlbumAssets,
  getGallery,
  type MediaItem,
  searchImages,
} from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";
import { useBodyScrollLock } from "@/lib/use-body-scroll-lock";

interface AlbumAssetPickerProps {
  albumId: number;
  existingIds: ReadonlySet<number>;
  onClose: () => void;
  onAdded: () => void;
}

export function AlbumAssetPicker({
  albumId,
  existingIds,
  onClose,
  onAdded,
}: AlbumAssetPickerProps) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const dialogRef = useRef<HTMLElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  useBodyScrollLock();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    openerRef.current = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      openerRef.current?.focus();
    };
  }, [onClose]);

  const mediaQuery = useQuery({
    queryKey: ["album-asset-picker", debouncedQuery],
    queryFn: async (): Promise<MediaItem[]> => {
      if (debouncedQuery) {
        const response = await searchImages({
          query: debouncedQuery,
          limit: 60,
        });
        return response.results.map((result) => ({
          ...result.metadata,
          id: result.media_id,
        }));
      }
      return (await getGallery({ limit: 60, sortOrder: "newest" })).items;
    },
  });

  const candidates = useMemo(
    () => (mediaQuery.data ?? []).filter((item) => !existingIds.has(item.id)),
    [existingIds, mediaQuery.data],
  );

  const addMutation = useMutation({
    mutationFn: () => addAlbumAssets(albumId, Array.from(selectedIds)),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["album", albumId] });
      void queryClient.invalidateQueries({
        queryKey: ["album-assets", albumId],
      });
      void queryClient.invalidateQueries({ queryKey: ["albums"] });
      toast.success(
        `Added ${result.added_count} photo${result.added_count === 1 ? "" : "s"}`,
      );
      onAdded();
      onClose();
    },
    onError: () => toast.error("Couldn't add photos to this album"),
  });

  const toggle = (id: number) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div
      className="fixed inset-0 z-[80] grid place-items-center bg-black/75 p-3 backdrop-blur-xl"
      role="dialog"
      aria-modal="true"
      aria-labelledby="album-picker-heading"
    >
      <button
        type="button"
        aria-label="Close photo picker"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
      />
      <section
        ref={dialogRef}
        tabIndex={-1}
        className="frost-panel relative flex max-h-[min(90dvh,800px)] w-full max-w-4xl flex-col overflow-hidden rounded-3xl bg-[color:var(--void)] outline-none"
      >
        <header className="flex items-center justify-between border-b border-[var(--frost)] px-5 py-4">
          <div>
            <h2 id="album-picker-heading" className="text-lg font-semibold">
              Add photos
            </h2>
            <p className="mt-1 text-xs text-[color:var(--silver)]">
              Search uses the same local semantic index as Find Search.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="icon-button"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="border-b border-[var(--frost)] p-4">
          <label className="flex h-11 items-center gap-2 rounded-xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-3">
            <Search className="h-4 w-4 text-[color:var(--muted)]" />
            <span className="sr-only">Search photos</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by scene, object, caption, or text"
              className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[color:var(--muted)]"
            />
          </label>
        </div>

        <div className="timeline-native-scroll min-h-56 flex-1 overflow-y-auto p-4">
          {mediaQuery.isPending ? (
            <div className="grid min-h-56 place-items-center text-sm text-[color:var(--silver)]">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : candidates.length === 0 ? (
            <div className="grid min-h-56 place-items-center text-center text-sm text-[color:var(--silver)]">
              {debouncedQuery
                ? "No matching photos outside this album."
                : "Every available photo is already in this album."}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
              {candidates.map((item) => {
                const selected = selectedIds.has(item.id);
                const src = resolveMediaUrl(
                  item.thumbnail_url ?? item.url,
                  item.minio_key,
                  item.id,
                  !item.thumbnail_url,
                );
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => toggle(item.id)}
                    aria-pressed={selected}
                    className="group relative aspect-square overflow-hidden rounded-xl border border-[var(--frost)] bg-[color:var(--surface-soft)] focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
                  >
                    {src ? (
                      // biome-ignore lint/performance/noImgElement: authenticated media URL.
                      <img
                        src={src}
                        alt={item.filename}
                        className="h-full w-full object-cover"
                      />
                    ) : null}
                    <span
                      className={`absolute right-2 top-2 grid size-6 place-items-center rounded-full border text-white ${
                        selected
                          ? "border-white bg-[color:var(--blue)]"
                          : "border-white/60 bg-black/45"
                      }`}
                    >
                      {selected && <Check className="h-3.5 w-3.5" />}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-[var(--frost)] px-5 py-4">
          <span className="text-sm text-[color:var(--silver)]">
            {selectedIds.size} selected
          </span>
          <button
            type="button"
            disabled={selectedIds.size === 0 || addMutation.isPending}
            onClick={() => addMutation.mutate()}
            className="white-pill px-4 py-2 text-sm font-semibold disabled:opacity-45"
          >
            {addMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Add to album
          </button>
        </footer>
      </section>
    </div>
  );
}
