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
import { TimelineMediaView } from "@/components/timeline-media-view";
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

export default function AlbumDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const albumId = Number(params?.id);
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

        {!assetsLoading && (
          <TimelineMediaView
            items={items}
            getId={(item) => item.id}
            getDate={(item) => item.created_at}
            getWidth={(item) => item.width}
            getHeight={(item) => item.height}
            getThumbnailUrl={(item) => `/api/image/${item.id}/thumbnail`}
            getOriginalUrl={(item) => `/api/image/${item.id}/original`}
            getAlt={(item) => item.filename}
            getItemTestId={(item) => `album-asset-${item.id}`}
            getOpenTestId={(item) => `open-asset-${item.id}`}
            empty={
              <p data-testid="album-empty" className="muted-copy">
                This album has no photos yet.
              </p>
            }
            renderItemActions={(item) => (
              <>
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
              </>
            )}
            renderViewer={({ viewerAssets, index, onIndexChange, onClose }) => (
              <AssetViewer
                assets={viewerAssets}
                index={index}
                onIndexChange={onIndexChange}
                onClose={onClose}
                favoriteIds={favoriteIds}
                onToggleFavorite={(id) => favoriteMutation.mutate(id)}
                onArchive={(id) => archiveMutation.mutate(id)}
                onTrash={(id) => trashMutation.mutate(id)}
              />
            )}
          />
        )}

        {!album && !albumLoading && (
          <p className="muted-copy">
            <ImageIcon size={16} className="mr-2 inline" />
            Album not found.
          </p>
        )}
      </div>
    </main>
  );
}
