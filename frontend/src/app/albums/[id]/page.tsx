"use client";

/**
 * Album detail page (frontend for the Phase 4.2 backend).
 * Shows an album's assets, lets the user remove assets and set a cover, and
 * delete the album. Adding assets from the gallery is a follow-on; this page
 * covers viewing + managing an existing album's contents.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ArrowLeft,
  FolderPlus,
  ImageIcon,
  Loader2,
  Share2,
  Star,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { AlbumAssetPicker } from "@/components/album-asset-picker";
import { AlbumShareLinks } from "@/components/album-share-links";
import { ImagePreviewModal } from "@/components/image-preview-modal";
import { TimelineMediaView } from "@/components/timeline-media-view";
import {
  deleteAlbum,
  getAlbum,
  getAlbumAssets,
  removeAlbumAssets,
  setArchive,
  trashImage,
  updateAlbum,
} from "@/lib/api";

export default function AlbumDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const albumId = Number(params?.id);
  const [removedIds, setRemovedIds] = useState<Set<number>>(new Set());
  const [shareOpen, setShareOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

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
    onSuccess: (_result, mediaId) => {
      setRemovedIds((current) => new Set(current).add(mediaId));
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

  const archiveMutation = useMutation({
    mutationFn: (mediaId: number) => setArchive(mediaId, true),
    onSuccess: ({ id }) => {
      setRemovedIds((cur) => new Set(cur).add(id));
      invalidate();
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
      invalidate();
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
          <div className="mb-6 flex flex-col gap-4 border-b border-[var(--frost)] pb-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="text-sm font-semibold text-[color:var(--blue)]">
                  Albums
                </span>
                <span aria-hidden="true" className="text-[color:var(--muted)]">
                  /
                </span>
                <h1 className="section-heading text-4xl font-medium">
                  {album.name}
                </h1>
              </div>
              {album.description && (
                <p className="muted-copy mt-1 text-sm">{album.description}</p>
              )}
              <p className="muted-copy mt-1 text-xs">
                {album.asset_count} photo{album.asset_count === 1 ? "" : "s"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="white-pill px-4 py-2 text-sm font-semibold"
              >
                <FolderPlus size={16} /> Add photos
              </button>
              <button
                type="button"
                onClick={() => setShareOpen((open) => !open)}
                aria-expanded={shareOpen}
                className="frost-button px-4 py-2 text-sm"
              >
                {shareOpen ? <X size={16} /> : <Share2 size={16} />}{" "}
                {shareOpen ? "Close sharing" : "Share"}
              </button>
              <button
                type="button"
                data-testid="delete-album"
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="frost-button px-4 py-2 text-sm text-[color:var(--silver)]"
              >
                <Trash2 size={16} /> Delete album
              </button>
            </div>
          </div>
        )}

        {Number.isFinite(albumId) && shareOpen && (
          <div className="frost-panel page-enter mb-8 rounded-2xl p-5">
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
            renderViewer={({
              items: viewerItems,
              index,
              onIndexChange,
              onClose,
            }) => {
              const active = viewerItems[index];
              if (!active) return null;
              return (
                <ImagePreviewModal
                  media={active}
                  onClose={onClose}
                  onPrevious={() => onIndexChange(index - 1)}
                  onNext={() => onIndexChange(index + 1)}
                  hasPrevious={index > 0}
                  hasNext={index < viewerItems.length - 1}
                  onDeleted={(id) => {
                    setRemovedIds((current) => new Set(current).add(id));
                    invalidate();
                  }}
                  actions={
                    <>
                      <button
                        type="button"
                        data-testid="preview-remove-from-album"
                        className="frost-button px-4 py-2 text-sm"
                        onClick={() => {
                          removeMutation.mutate(active.id);
                          onClose();
                        }}
                      >
                        <X className="h-4 w-4" /> Remove from album
                      </button>
                      <button
                        type="button"
                        data-testid="preview-archive"
                        className="frost-button px-4 py-2 text-sm"
                        onClick={() => {
                          archiveMutation.mutate(active.id);
                          onClose();
                        }}
                      >
                        <Archive className="h-4 w-4" /> Archive
                      </button>
                      <button
                        type="button"
                        data-testid="preview-trash"
                        className="frost-button px-4 py-2 text-sm"
                        onClick={() => {
                          trashMutation.mutate(active.id);
                          onClose();
                        }}
                      >
                        <Trash2 className="h-4 w-4" /> Move to trash
                      </button>
                    </>
                  }
                />
              );
            }}
          />
        )}

        {!album && !albumLoading && (
          <p className="muted-copy">
            <ImageIcon size={16} className="mr-2 inline" />
            Album not found.
          </p>
        )}

        {pickerOpen && Number.isFinite(albumId) && (
          <AlbumAssetPicker
            albumId={albumId}
            existingIds={new Set(items.map((item) => item.id))}
            onClose={() => setPickerOpen(false)}
            onAdded={invalidate}
          />
        )}
      </div>
    </main>
  );
}
