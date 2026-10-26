"use client";

interface LoadMoreButtonProps {
  shown: number;
  total: number;
  loading: boolean;
  onLoadMore: () => void;
}

/** "Load more" under a paged list, with how much of it is on screen. */
export function LoadMoreButton({
  shown,
  total,
  loading,
  onLoadMore,
}: LoadMoreButtonProps) {
  return (
    <div className="mt-8 flex flex-col items-center gap-2">
      <button
        type="button"
        onClick={onLoadMore}
        disabled={loading}
        className="frost-button inline-flex items-center gap-2 px-6 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Loading more…" : "Load more"}
      </button>
      <p className="text-xs text-[color:var(--silver)]">
        Showing {shown} of {total}
      </p>
    </div>
  );
}

/** Next skip for a skip/limit list, or undefined once every row is loaded. */
export function nextSkip<T>(
  pages: readonly T[],
  rowsIn: (page: T) => number,
  total: number,
): number | undefined {
  const loaded = pages.reduce((sum, page) => sum + rowsIn(page), 0);
  return loaded < total ? loaded : undefined;
}
