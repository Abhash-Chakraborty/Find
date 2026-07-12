"use client";

/**
 * Archive page (frontend for Phase 4.4 backend).
 * Lists archived media (kept but hidden from the main timeline); supports
 * unarchive (send back to the timeline).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Loader2 } from "lucide-react";
import { toast } from "sonner";
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
        <h1 className="section-heading mb-6 text-4xl font-medium">Archive</h1>

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
          />
        )}
      </div>
    </main>
  );
}
