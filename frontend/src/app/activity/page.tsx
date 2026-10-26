"use client";

/**
 * Activity page — local, privacy-safe log of upload, archive/trash/restore,
 * vault, and settings events (frontend for the `/api/activity` backend PR).
 */

import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Image as ImageIcon,
  Loader2,
  LockKeyhole,
  type LucideIcon,
  RefreshCw,
  Settings as SettingsIcon,
  Trash2,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  activityTone,
  describeActivity,
  groupActivityByDay,
} from "@/lib/activity";
import {
  type ActivityItem,
  clearActivity,
  getActivity,
  purgeActivity,
} from "@/lib/api";

const ACTIVITY_LIMIT = 50;

const CATEGORIES = [
  { value: undefined, label: "All" },
  { value: "upload", label: "Uploads" },
  { value: "media", label: "Media" },
  { value: "vault", label: "Vault" },
  { value: "settings", label: "Settings" },
] as const;

const CATEGORY_ICON: Record<string, LucideIcon> = {
  upload: UploadCloud,
  media: ImageIcon,
  vault: LockKeyhole,
  settings: SettingsIcon,
};

const TONE_CLASS = {
  positive: "status-indexed",
  negative: "status-failed",
  neutral: "status-pending",
} as const;

function formatTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function ActivityRow({ item }: { item: ActivityItem }) {
  const Icon = CATEGORY_ICON[item.category] ?? SettingsIcon;
  return (
    <li
      data-testid={`activity-item-${item.id}`}
      className="flex items-start gap-3 rounded-xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)] p-3"
    >
      <span
        className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${TONE_CLASS[activityTone(item)]}`}
      >
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-[color:var(--near-white)]">
          {describeActivity(item)}
          {item.media_id !== null && (
            <Link
              href={`/image/${item.media_id}`}
              className="ml-2 text-xs font-medium text-[color:var(--blue)] hover:underline"
            >
              View
            </Link>
          )}
        </p>
        <p className="mt-0.5 text-xs text-[color:var(--muted)]">
          {formatTime(item.created_at)}
        </p>
      </div>
    </li>
  );
}

export default function ActivityPage() {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<string | undefined>(undefined);

  const queryKey = ["activity", category] as const;

  const {
    data,
    isLoading,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) =>
      getActivity({ skip: pageParam, limit: ACTIVITY_LIMIT, category }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      // The feed is newest-first and append-only, so a row recorded while the
      // user is paging shifts every later offset down by one. Measure that
      // drift against the first page's total and push the next offset past it,
      // otherwise "Load more" re-serves rows already on screen and skips the
      // same number of older ones.
      const consumed = allPages.reduce(
        (n, page) => n + (page?.items.length ?? 0),
        0,
      );
      const snapshotTotal = allPages[0]?.total ?? lastPage?.total ?? 0;
      const drift = Math.max(0, (lastPage?.total ?? 0) - snapshotTotal);
      return consumed < snapshotTotal ? consumed + drift : undefined;
    },
  });

  // Retention is enforced whenever Activity is opened, mirroring Trash's
  // auto-purge-on-view (see get_trash / purge_expired_trash on the backend).
  // The initial GET can win the race against this delete, so refresh once it
  // has actually removed something.
  useEffect(() => {
    void purgeActivity()
      .then((res) => {
        if (res.deleted_count > 0) {
          queryClient.invalidateQueries({ queryKey: ["activity"] });
        }
      })
      .catch(() => {
        // Best-effort: an idle purge failing shouldn't block viewing activity.
      });
  }, [queryClient]);

  const clearMutation = useMutation({
    mutationFn: clearActivity,
    onSuccess: (res) => {
      toast.success(`Cleared ${res.deleted_count} item(s)`);
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
    onError: () => toast.error("Couldn't clear activity"),
  });

  // Offset paging over a live feed can still overlap at the seams, so drop
  // ids already rendered rather than letting a row appear twice.
  const items = useMemo(() => {
    const seen = new Set<number>();
    const flat: ActivityItem[] = [];
    for (const page of data?.pages ?? []) {
      for (const item of page.items) {
        if (!seen.has(item.id)) {
          seen.add(item.id);
          flat.push(item);
        }
      }
    }
    return flat;
  }, [data]);
  const total = data?.pages[0]?.total ?? 0;
  const days = groupActivityByDay(items);

  return (
    <main className="page-shell">
      <div className="container-shell py-10 md:py-14">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-[color:var(--frost)] pb-5">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-sm font-semibold text-[color:var(--blue)]">
              Utilities
            </span>
            <span aria-hidden="true" className="text-[color:var(--muted)]">
              /
            </span>
            <h1 className="section-heading text-4xl font-medium">Activity</h1>
            <span className="text-sm text-[color:var(--silver)]">
              {total} events
            </span>
          </div>
          {items.length > 0 && (
            <button
              type="button"
              data-testid="clear-activity"
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending}
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--frost)] px-4 py-2 text-sm text-[color:var(--silver)] hover:text-[color:var(--near-white)] disabled:opacity-50"
            >
              <Trash2 size={16} /> Clear
            </button>
          )}
        </div>

        <fieldset className="mb-6 flex flex-wrap gap-2 border-0 p-0">
          <legend className="sr-only">Filter by category</legend>
          {CATEGORIES.map(({ value, label }) => (
            <button
              key={label}
              type="button"
              aria-pressed={category === value}
              onClick={() => setCategory(value)}
              className={`rounded-full border px-3.5 py-1.5 text-sm transition ${
                category === value
                  ? "border-[color:var(--near-white)] bg-[color:var(--near-white)] text-[color:var(--void)]"
                  : "border-[color:var(--frost)] text-[color:var(--silver)] hover:bg-[color:var(--surface-hover)]"
              }`}
            >
              {label}
            </button>
          ))}
        </fieldset>

        {isLoading && (
          <div
            className="space-y-2"
            role="status"
            aria-label="Loading activity"
            aria-busy="true"
          >
            {[0, 1, 2, 3].map((row) => (
              <div
                key={row}
                className="h-14 animate-pulse rounded-xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)]"
              />
            ))}
          </div>
        )}

        {!isLoading && isError && (
          <section
            role="alert"
            className="rounded-2xl border border-[color:var(--red)]/30 bg-[color:var(--red-soft)] p-6"
          >
            <h2 className="text-base font-semibold">
              Couldn&apos;t load activity
            </h2>
            <p className="mt-2 text-sm leading-6 text-[color:var(--silver)]">
              Check the local API and try again.
            </p>
            <button
              type="button"
              data-testid="activity-retry"
              onClick={() => refetch()}
              className="mt-5 inline-flex h-10 items-center gap-2 rounded-xl bg-[color:var(--near-white)] px-4 text-sm font-semibold text-[color:var(--void)] outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
            >
              <RefreshCw aria-hidden="true" size={15} />
              Retry
            </button>
          </section>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <p data-testid="activity-empty" className="muted-copy">
            No activity yet.
          </p>
        )}

        {!isLoading && !isError && items.length > 0 && (
          <div className="space-y-6">
            {days.map((day) => (
              <div key={day.label}>
                <h2 className="mb-2 text-sm font-semibold text-[color:var(--silver)]">
                  {day.label}
                </h2>
                <ul className="space-y-2">
                  {day.items.map((item) => (
                    <ActivityRow key={item.id} item={item} />
                  ))}
                </ul>
              </div>
            ))}

            {hasNextPage && (
              <div className="flex flex-col items-center gap-2 pt-4">
                <button
                  type="button"
                  onClick={() => void fetchNextPage()}
                  disabled={isFetchingNextPage}
                  className="frost-button inline-flex items-center gap-2 px-6 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isFetchingNextPage ? (
                    <Loader2
                      className="h-4 w-4 animate-spin"
                      aria-hidden="true"
                    />
                  ) : null}
                  {isFetchingNextPage ? "Loading more…" : "Load more"}
                </button>
                <p className="text-xs text-[color:var(--silver)]">
                  Showing {items.length} of {total}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
