"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import { useEffect, useState } from "react";
import {
  type DuplicatePair,
  deleteImage,
  getDuplicates,
  keepBothDuplicateImages,
} from "@/lib/api";
import { getFallbackImageUrl, resolveMediaUrl } from "@/lib/media";

const PAGE_SIZE = 20;

function DuplicateImage({
  id,
  name,
  label,
}: {
  id: number;
  name: string;
  label: string;
}) {
  return (
    <div className="min-w-0 space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-[color:var(--muted)]">
        {label}
      </p>
      <div className="relative aspect-square overflow-hidden rounded-lg border border-[var(--frost)] bg-[color:var(--surface-soft)]">
        <Image
          src={resolveMediaUrl(null, null, id, true) ?? getFallbackImageUrl()}
          alt={name}
          fill
          sizes="(max-width: 768px) 50vw, 220px"
          unoptimized
          className="object-cover"
          onError={(event) => {
            event.currentTarget.src = getFallbackImageUrl();
          }}
        />
      </div>
      <p className="truncate text-xs text-[color:var(--silver)]" title={name}>
        {name}
      </p>
    </div>
  );
}

function DuplicateCard({
  pair,
  onDelete,
  onKeepBoth,
  isDeleting,
  isKeeping,
}: {
  pair: DuplicatePair;
  onDelete: (mediaId: number) => void;
  onKeepBoth: (mediaId: number) => void;
  isDeleting: boolean;
  isKeeping: boolean;
}) {
  return (
    <article className="rounded-xl border border-[var(--frost)] bg-[color:var(--frost-soft)] p-4 shadow-sm">
      <div className="grid grid-cols-2 gap-4">
        <DuplicateImage
          id={pair.original_id}
          name={pair.original_name}
          label="Original"
        />
        <DuplicateImage
          id={pair.duplicate_id}
          name={pair.duplicate_name}
          label="Near-duplicate"
        />
      </div>

      <div className="mt-4 grid gap-2 border-t border-[var(--frost)] pt-4 sm:grid-cols-3">
        <button
          type="button"
          onClick={() => onDelete(pair.duplicate_id)}
          disabled={isDeleting}
          className="rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-500/15 disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-200"
        >
          Delete duplicate
        </button>
        <button
          type="button"
          onClick={() => onDelete(pair.original_id)}
          disabled={isDeleting}
          className="rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-500/15 disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-200"
        >
          Delete original
        </button>
        <button
          type="button"
          onClick={() => onKeepBoth(pair.duplicate_id)}
          disabled={isKeeping}
          className="rounded-lg border border-[var(--frost)] bg-[color:var(--surface-soft)] px-3 py-2 text-sm font-medium text-[color:var(--near-white)] transition hover:bg-[color:var(--frost-soft)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          Keep both
        </button>
      </div>
    </article>
  );
}

export default function DuplicatesPage() {
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["duplicates", page],
    queryFn: () => getDuplicates({ page, limit: PAGE_SIZE }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteImage,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["duplicates"] });
    },
  });

  const keepBothMutation = useMutation({
    mutationFn: keepBothDuplicateImages,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["duplicates"] });
    },
  });

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  useEffect(() => {
    setPage((currentPage) => Math.min(currentPage, totalPages));
  }, [totalPages]);

  if (isLoading) {
    return (
      <main className="container-shell flex min-h-[60vh] items-center justify-center py-10">
        <p className="text-sm text-[color:var(--silver)]">
          Loading duplicates...
        </p>
      </main>
    );
  }

  if (isError) {
    return (
      <main className="container-shell flex min-h-[60vh] items-center justify-center py-10">
        <p className="text-sm font-medium text-red-700 dark:text-red-200">
          Failed to load duplicates.
        </p>
      </main>
    );
  }

  const pairs = data?.items ?? [];

  return (
    <main className="container-shell py-10">
      <section className="mb-6">
        <h1 className="section-heading">Near-Duplicate Images</h1>
        <p className="mt-2 text-sm text-[color:var(--silver)]">
          {data?.total ?? 0} near-duplicate pairs found
        </p>
      </section>

      {pairs.length === 0 ? (
        <section className="rounded-xl border border-[var(--frost)] bg-[color:var(--frost-soft)] px-6 py-14 text-center">
          <p className="text-base font-medium text-[color:var(--near-white)]">
            No near-duplicates found.
          </p>
          <p className="mt-2 text-sm text-[color:var(--silver)]">
            Upload more images to detect visually similar pairs.
          </p>
        </section>
      ) : (
        <section className="grid gap-4 lg:grid-cols-2">
          {pairs.map((pair) => (
            <DuplicateCard
              key={pair.duplicate_id}
              pair={pair}
              onDelete={(mediaId) => deleteMutation.mutate(mediaId)}
              onKeepBoth={(mediaId) => keepBothMutation.mutate(mediaId)}
              isDeleting={deleteMutation.isPending}
              isKeeping={keepBothMutation.isPending}
            />
          ))}
        </section>
      )}

      {totalPages > 1 && (
        <nav
          className="mt-8 flex items-center justify-center gap-3"
          aria-label="Duplicate image pages"
        >
          <button
            type="button"
            onClick={() =>
              setPage((currentPage) => Math.max(1, currentPage - 1))
            }
            disabled={page === 1}
            className="frost-button disabled:cursor-not-allowed disabled:opacity-45"
          >
            Previous
          </button>
          <span className="min-w-20 text-center text-sm text-[color:var(--silver)]">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() =>
              setPage((currentPage) => Math.min(totalPages, currentPage + 1))
            }
            disabled={page === totalPages}
            className="frost-button disabled:cursor-not-allowed disabled:opacity-45"
          >
            Next
          </button>
        </nav>
      )}
    </main>
  );
}
