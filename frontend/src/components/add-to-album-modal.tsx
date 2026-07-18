"use client";

/**
 * Add-to-album modal — pick an existing album (or create one) and add the
 * currently-selected gallery media to it. Closes the gap where album
 * membership could previously only shrink (the backend `addAlbumAssets`
 * endpoint had no UI entry point).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderPlus, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { addAlbumAssets, createAlbum, getAlbums } from "@/lib/api";

interface AddToAlbumModalProps {
  mediaIds: number[];
  onClose: () => void;
  onAdded?: () => void;
}

export function AddToAlbumModal({
  mediaIds,
  onClose,
  onAdded,
}: AddToAlbumModalProps) {
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState("");

  // Close on Escape, matching the AssetViewer's modal keyboard behavior.
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const { data, isLoading } = useQuery({
    queryKey: ["albums"],
    queryFn: getAlbums,
  });

  const addMutation = useMutation({
    mutationFn: (albumId: number) => addAlbumAssets(albumId, mediaIds),
    onSuccess: (res, albumId) => {
      queryClient.invalidateQueries({ queryKey: ["albums"] });
      queryClient.invalidateQueries({ queryKey: ["album", albumId] });
      queryClient.invalidateQueries({ queryKey: ["album-assets", albumId] });
      toast.success(
        `Added ${res.added_count} photo${res.added_count === 1 ? "" : "s"}`,
      );
      onAdded?.();
      onClose();
    },
    onError: () => toast.error("Couldn't add to album"),
  });

  const createAndAddMutation = useMutation({
    mutationFn: async (name: string) => {
      const album = await createAlbum({ name });
      await addAlbumAssets(album.id, mediaIds);
      return album;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["albums"] });
      toast.success("Album created and photos added");
      onAdded?.();
      onClose();
    },
    onError: () => toast.error("Couldn't create album"),
  });

  const albums = data?.albums ?? [];
  const busy = addMutation.isPending || createAndAddMutation.isPending;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Add to album"
      data-testid="add-to-album-modal"
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-md rounded-2xl border border-[var(--frost)] bg-[color:var(--void)] p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-medium">
            Add {mediaIds.length} photo{mediaIds.length === 1 ? "" : "s"} to
            album
          </h2>
          <button
            type="button"
            aria-label="Close"
            data-testid="add-to-album-close"
            onClick={onClose}
            className="rounded-full p-1.5"
          >
            <X size={18} />
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            const name = newName.trim();
            if (name) {
              createAndAddMutation.mutate(name);
            }
          }}
          className="mb-4 flex gap-2"
        >
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New album name"
            aria-label="New album name"
            maxLength={255}
            className="flex-1 rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] px-4 py-2 text-sm"
          />
          <button
            type="submit"
            data-testid="create-and-add"
            disabled={!newName.trim() || busy}
            className="inline-flex items-center gap-2 rounded-full border border-[var(--frost)] px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            <FolderPlus size={16} /> Create
          </button>
        </form>

        {isLoading && (
          <div role="status" aria-label="Loading albums">
            <Loader2 className="animate-spin" />
          </div>
        )}

        {!isLoading && albums.length === 0 && (
          <p data-testid="no-albums-hint" className="muted-copy text-sm">
            No albums yet — create one above.
          </p>
        )}

        <ul className="max-h-64 overflow-y-auto">
          {albums.map((album) => (
            <li key={album.id}>
              <button
                type="button"
                data-testid={`pick-album-${album.id}`}
                disabled={busy}
                onClick={() => addMutation.mutate(album.id)}
                className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition hover:bg-[color:var(--frost-soft)] disabled:opacity-50"
              >
                <span>{album.name}</span>
                <span className="muted-copy text-xs">
                  {album.asset_count} photo{album.asset_count === 1 ? "" : "s"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
