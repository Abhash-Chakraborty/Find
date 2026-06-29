"use client";

/**
 * Trash page (frontend for Phase 4.4 backend).
 * Lists soft-deleted media; supports restore (per-item) and empty-trash
 * (permanent delete of all). Trashed assets are excluded from the main gallery.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { emptyTrash, getTrash, restoreImage } from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";

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
        <div className="mb-6 flex items-center justify-between">
          <h1 className="section-heading text-4xl font-medium">Trash</h1>
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

        {!isLoading && !isError && items.length === 0 && (
          <p data-testid="trash-empty" className="muted-copy">
            Trash is empty.
          </p>
        )}

        <ul className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-5">
          {items.map((item) => (
            <li
              key={item.id}
              data-testid={`trash-item-${item.id}`}
              className="group relative aspect-square overflow-hidden rounded-xl bg-[color:var(--surface-soft)]"
            >
              {/* biome-ignore lint/a11y/useAltText: trash tile */}
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
                className="h-full w-full object-cover opacity-70"
              />
              <button
                type="button"
                aria-label="Restore image"
                data-testid={`restore-${item.id}`}
                onClick={() => restoreMutation.mutate(item.id)}
                className="absolute bottom-1 right-1 flex items-center gap-1 rounded-full bg-black/60 px-2 py-1 text-xs text-white opacity-0 transition group-hover:opacity-100"
              >
                <RotateCcw size={12} /> Restore
              </button>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
