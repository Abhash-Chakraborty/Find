"use client";

/**
 * Archive page (frontend for Phase 4.4 backend).
 * Lists archived media (kept but hidden from the main timeline); supports
 * unarchive (send back to the timeline).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { getArchive, setArchive } from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";

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

        {!isLoading && !isError && items.length === 0 && (
          <p data-testid="archive-empty" className="muted-copy">
            No archived photos.
          </p>
        )}

        <ul className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-5">
          {items.map((item) => (
            <li
              key={item.id}
              data-testid={`archive-item-${item.id}`}
              className="group relative aspect-square overflow-hidden rounded-xl bg-[color:var(--surface-soft)]"
            >
              {/* biome-ignore lint/performance/noImgElement: thumbnail tile, not a Next-optimized route */}
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
              <button
                type="button"
                aria-label="Unarchive image"
                data-testid={`unarchive-${item.id}`}
                onClick={() => unarchiveMutation.mutate(item.id)}
                className="absolute bottom-1 right-1 flex items-center gap-1 rounded-full bg-black/60 px-2 py-1 text-xs text-white opacity-0 transition group-hover:opacity-100"
              >
                <ArchiveRestore size={12} /> Unarchive
              </button>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
