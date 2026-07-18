"use client";

/**
 * Trash page (frontend for Phase 4.4 backend).
 * Lists soft-deleted media; supports restore (per-item) and empty-trash
 * (permanent delete of all). Trashed assets are excluded from the main gallery.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ImagePreviewModal } from "@/components/image-preview-modal";
import { TimelineMediaView } from "@/components/timeline-media-view";
import { emptyTrash, getTrash, restoreImage } from "@/lib/api";

export default function TrashPage() {
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["trash"],
    queryFn: () => getTrash(),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["trash"] });
    queryClient.invalidateQueries({ queryKey: ["gallery-infinite"] });
    queryClient.invalidateQueries({ queryKey: ["gallery-counts"] });
  };

  const restoreMutation = useMutation({
    mutationFn: (mediaId: number) => restoreImage(mediaId),
    onSuccess: () => {
      invalidate();
      toast.success("Restored");
    },
    onError: () => toast.error("Couldn't restore"),
  });

  const emptyMutation = useMutation({
    mutationFn: () => emptyTrash(),
    onSuccess: (res) => {
      invalidate();
      toast.success(`Permanently deleted ${res.deleted_count} item(s)`);
    },
    onError: () => toast.error("Couldn't empty trash"),
  });

  const items = data?.items ?? [];

  return (
    <main className="page-shell">
      <div className="container-shell py-10 md:py-14">
        <div className="mb-6 flex items-end justify-between gap-4 border-b border-[var(--frost)] pb-5">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-sm font-semibold text-[color:var(--blue)]">
              Utilities
            </span>
            <span aria-hidden="true" className="text-[color:var(--muted)]">
              /
            </span>
            <h1 className="section-heading text-4xl font-medium">Trash</h1>
            <span className="text-sm text-[color:var(--silver)]">
              {items.length} photos
            </span>
          </div>
          {items.length > 0 && (
            <button
              type="button"
              data-testid="empty-trash"
              onClick={() => emptyMutation.mutate()}
              disabled={emptyMutation.isPending}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--frost)] px-4 py-2 text-sm text-[color:var(--silver)] hover:text-[color:var(--near-white)] disabled:opacity-50"
            >
              <Trash2 size={16} /> Empty trash
            </button>
          )}
        </div>

        {isLoading && (
          <div role="status" aria-label="Loading trash">
            <Loader2 className="animate-spin" />
          </div>
        )}

        {!isLoading && isError && (
          <p data-testid="trash-error" role="alert" className="muted-copy">
            Couldn't load the trash. Please try again.
          </p>
        )}

        {!isLoading && !isError && (
          <TimelineMediaView
            items={items}
            getId={(item) => item.id}
            getDate={(item) => item.created_at}
            getWidth={(item) => item.width}
            getHeight={(item) => item.height}
            getThumbnailUrl={(item) => `/api/image/${item.id}/thumbnail`}
            getOriginalUrl={(item) => `/api/image/${item.id}/original`}
            getAlt={(item) => item.filename}
            getItemTestId={(item) => `trash-item-${item.id}`}
            getOpenTestId={(item) => `open-trash-${item.id}`}
            empty={
              <p data-testid="trash-empty" className="muted-copy">
                Trash is empty.
              </p>
            }
            renderItemActions={(item) => (
              <button
                type="button"
                aria-label="Restore image"
                data-testid={`restore-${item.id}`}
                onClick={() => restoreMutation.mutate(item.id)}
                disabled={
                  restoreMutation.isPending &&
                  restoreMutation.variables === item.id
                }
                className="flex items-center gap-1 rounded-full bg-black/70 px-2 py-1 text-xs text-white disabled:opacity-50"
              >
                <RotateCcw size={12} /> Restore
              </button>
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
                  actions={
                    <button
                      type="button"
                      className="white-pill px-4 py-2 text-sm font-semibold"
                      onClick={() => {
                        restoreMutation.mutate(active.id);
                        onClose();
                      }}
                    >
                      <RotateCcw className="h-4 w-4" /> Restore to Photos
                    </button>
                  }
                />
              );
            }}
          />
        )}
      </div>
    </main>
  );
}
