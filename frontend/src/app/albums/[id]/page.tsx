"use client";

/**
 * Album detail page (frontend for the Phase 4.2 backend).
 * Shows an album's assets, lets the user remove assets and set a cover, and
 * delete the album. Adding assets from the gallery is a follow-on; this page
 * covers viewing + managing an existing album's contents.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ImageIcon, Loader2, Star, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { AlbumShareLinks } from "@/components/album-share-links";
import { AssetViewer } from "@/components/asset-viewer";
import {
  deleteAlbum,
  getAlbum,
  getAlbumAssets,
  removeAlbumAssets,
  setArchive,
  toggleLike,
  trashImage,
  updateAlbum,
} from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";

export default function AlbumDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const albumId = Number(params?.id);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [removedIds, setRemovedIds] = useState<Set<number>>(new Set());

  const { data: album, isLoading: albumLoading } = useQuery({
    queryKey: ["album", albumId],
    queryFn: () => getAlbum(albumId),
    enabled: Number.isFinite(albumId),
  });

  const { data: assetsData, isLoading: assetsLoading } = useQuery({
    queryKey: ["album-assets", albumId],
    queryFn: () => getAlbumAssets(albumId),
    enabled: Number.isFinite(albumId),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["album", albumId] });
    queryClient.invalidateQueries({ queryKey: ["album-assets", albumId] });
    queryClient.invalidateQueries({ queryKey: ["albums"] });
  };

  const removeMutation = useMutation({
    mutationFn: (mediaId: number) => removeAlbumAssets(albumId, [mediaId]),
    onSuccess: () => {
      invalidate();
      toast.success("Removed from album");
    },
    onError: () => toast.error("Couldn't remove image"),
  });

  const coverMutation = useMutation({
    mutationFn: (mediaId: number) =>
      updateAlbum(albumId, { cover_media_id: mediaId }),
    onSuccess: () => {
      invalidate();
      toast.success("Cover updated");
    },
    onError: () => toast.error("Couldn't set cover"),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteAlbum(albumId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["albums"] });
      toast.success("Album deleted");
      router.push("/albums");
    },
    onError: () => toast.error("Couldn't delete album"),
  });

  const favoriteMutation = useMutation({
    mutationFn: (mediaId: number) => toggleLike(mediaId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["album-assets", albumId] });
    },
    onError: () => toast.error("Couldn't update favorite"),
  });

  const archiveMutation = useMutation({
    mutationFn: (mediaId: number) => setArchive(mediaId, true),
    onSuccess: ({ id }) => {
      setRemovedIds((cur) => new Set(cur).add(id));
      queryClient.invalidateQueries({ queryKey: ["album-assets", albumId] });
      queryClient.invalidateQueries({ queryKey: ["archive"] });
      toast.success("Archived");
    },
    onError: () => toast.error("Couldn't archive"),
  });

  const trashMutation = useMutation({
    mutationFn: (mediaId: number) => trashImage(mediaId),
    onSuccess: ({ id }) => {
      setRemovedIds((cur) => new Set(cur).add(id));
      queryClient.invalidateQueries({ queryKey: ["album-assets", albumId] });
      queryClient.invalidateQueries({ queryKey: ["trash"] });
      toast.success("Moved to trash");
    },
    onError: () => toast.error("Couldn't move to trash"),
  });

  // Assets archived/trashed from the viewer leave the album view immediately
  // (they also fall out of the browsable query on refetch).
  const allItems = assetsData?.items ?? [];
  const items = allItems.filter((item) => !removedIds.has(item.id));
  const favoriteIds = new Set(
    items.filter((item) => item.liked).map((item) => item.id),
  );

  return (
    <main className="page-shell">
      <div className="container-shell py-10 md:py-14">
        <Link
          href="/albums"
          className="mb-6 inline-flex items-center gap-2 text-sm text-[color:var(--silver)]"
        >
          <ArrowLeft size={16} /> All albums
        </Link>

        {albumLoading && (
          <div role="status" aria-label="Loading album">
            <Loader2 className="animate-spin" />
          </div>
        )}

        {album && (
          <div className="mb-8 flex items-start justify-between gap-4">
            <div>
              <h1 className="section-heading text-4xl font-medium">
                {album.name}
              </h1>
              {album.description && (
                <p className="muted-copy mt-1 text-sm">{album.description}</p>
              )}
              <p className="muted-copy mt-1 text-xs">
                {album.asset_count} photo{album.asset_count === 1 ? "" : "s"}
              </p>
            </div>
            <button
              type="button"
              data-testid="delete-album"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--frost)] px-4 py-2 text-sm text-[color:var(--silver)] transition hover:text-[color:var(--near-white)]"
            >
              <Trash2 size={16} /> Delete album
            </button>
          </div>
        )}

        {Number.isFinite(albumId) && (
          <div className="mb-8">
            <AlbumShareLinks albumId={albumId} />
          </div>
        )}

        {assetsLoading && (
          <div role="status" aria-label="Loading album images">
            <Loader2 className="animate-spin" />
          </div>
        )}

        {!assetsLoading && items.length === 0 && (
          <p data-testid="album-empty" className="muted-copy">
            This album has no photos yet.
          </p>
        )}

        <ul className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-5">
          {items.map((item, index) => (
            <li
              key={item.id}
              data-testid={`album-asset-${item.id}`}
              className="group relative aspect-square overflow-hidden rounded-xl bg-[color:var(--surface-soft)]"
            >
              <button
                type="button"
                aria-label={`Open ${item.filename}`}
                data-testid={`open-asset-${item.id}`}
                onClick={() => setViewerIndex(index)}
                className="block h-full w-full"
              >
                {/* biome-ignore lint/a11y/useAltText: album tile */}
                <img
                  src={
                    resolveMediaUrl(
                      item.thumbnail_url,
                      item.minio_key,
                      item.id,
                      true,
                    ) ?? undefined
                  }
                  alt={item.filename}
                  className="h-full w-full object-cover"
                />
              </button>
              <div className="absolute inset-x-0 bottom-0 flex justify-end gap-1 p-1 opacity-0 transition group-hover:opacity-100">
                <button
                  type="button"
                  aria-label="Set as cover"
                  data-testid={`set-cover-${item.id}`}
                  onClick={() => coverMutation.mutate(item.id)}
                  className="rounded-full bg-black/60 p-1.5 text-white"
                >
                  <Star size={14} />
                </button>
                <button
                  type="button"
                  aria-label="Remove from album"
                  data-testid={`remove-asset-${item.id}`}
                  onClick={() => removeMutation.mutate(item.id)}
                  className="rounded-full bg-black/60 p-1.5 text-white"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>

        {!album && !albumLoading && (
          <p className="muted-copy">
            <ImageIcon size={16} className="mr-2 inline" />
            Album not found.
          </p>
        )}
      </div>

      {viewerIndex !== null && items[viewerIndex] && (
        <AssetViewer
          assets={items.map((item) => ({
            id: item.id,
            thumbnailUrl: `/api/image/${item.id}/thumbnail`,
            originalUrl: `/api/image/${item.id}`,
          }))}
          index={viewerIndex}
          onIndexChange={setViewerIndex}
          onClose={() => setViewerIndex(null)}
          favoriteIds={favoriteIds}
          onToggleFavorite={(id) => favoriteMutation.mutate(id)}
          onArchive={(id) => archiveMutation.mutate(id)}
          onTrash={(id) => trashMutation.mutate(id)}
        />
      )}
    </main>
  );
}
