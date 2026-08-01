"use client";

/**
 * Archive page (frontend for Phase 4.4 backend).
 * Lists archived media (kept but hidden from the main timeline); supports
 * unarchive (send back to the timeline).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { ImagePreviewModal } from "@/components/image-preview-modal";
import { TimelineMediaView } from "@/components/timeline-media-view";
import { getArchive, setArchive } from "@/lib/api";

export default function ArchivePage() {
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["archive"],
    queryFn: () => getArchive(),
  });

  const unarchiveMutation = useMutation({
    mutationFn: (mediaId: number) => setArchive(mediaId, false),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive"] });
      queryClient.invalidateQueries({ queryKey: ["gallery-infinite"] });
      queryClient.invalidateQueries({ queryKey: ["gallery-counts"] });
      toast.success("Unarchived");
    },
    onError: () => toast.error("Couldn't unarchive"),
  });

  const items = data?.items ?? [];

  return (
    <main className="page-shell">
      <div className="container-shell py-10 md:py-14">
        <header className="mb-6 flex items-baseline gap-2 border-b border-[var(--frost)] pb-5">
          <span className="text-sm font-semibold text-[color:var(--blue)]">
            Utilities
          </span>
          <span aria-hidden="true" className="text-[color:var(--muted)]">
            /
          </span>
          <h1 className="section-heading text-4xl font-medium">Archive</h1>
          <span className="text-sm text-[color:var(--silver)]">
            {items.length} photos
          </span>
        </header>

        {isLoading && (
          <div role="status" aria-label="Loading archive">
            <Loader2 className="animate-spin" />
          </div>
        )}

        {!isLoading && isError && (
          <p data-testid="archive-error" role="alert" className="muted-copy">
            Couldn't load the archive. Please try again.
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
            getItemTestId={(item) => `archive-item-${item.id}`}
            getOpenTestId={(item) => `open-archive-${item.id}`}
            empty={
              <p data-testid="archive-empty" className="muted-copy">
                No archived photos.
              </p>
            }
            renderItemActions={(item) => (
              <button
                type="button"
                aria-label="Unarchive image"
                data-testid={`unarchive-${item.id}`}
                onClick={() => unarchiveMutation.mutate(item.id)}
                disabled={
                  unarchiveMutation.isPending &&
                  unarchiveMutation.variables === item.id
                }
                className="flex items-center gap-1 rounded-full bg-black/70 px-2 py-1 text-xs text-white disabled:opacity-50"
              >
                <ArchiveRestore size={12} /> Unarchive
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
                        unarchiveMutation.mutate(active.id);
                        onClose();
                      }}
                    >
                      <ArchiveRestore className="h-4 w-4" /> Restore to Photos
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
