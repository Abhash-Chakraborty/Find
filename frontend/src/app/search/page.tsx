"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ImageOff,
  Loader2,
  Search as SearchIcon,
} from "lucide-react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { FeedbackRating } from "@/components/feedback-rating";
import { ImagePreviewModal } from "@/components/image-preview-modal";
import {
  getGallery,
  type SearchResult,
  searchImages,
  submitSearchRating,
} from "@/lib/api";
import { MINIO_URL_REFRESH_INTERVAL_MS, resolveMediaUrl } from "@/lib/media";

function SearchPageContent() {
  const searchParams = useSearchParams();
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [allResults, setAllResults] = useState<SearchResult[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [currentSkip, setCurrentSkip] = useState(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const initializedFromUrlRef = useRef(false);

  const LIMIT = 24;
  const recentQuery = useQuery({
    queryKey: ["search-recent-uploads"],
    queryFn: () => getGallery({ limit: 24, sortOrder: "newest" }),
    staleTime: 30_000,
  });

  const searchMutation = useMutation({
    mutationFn: async (params: {
      searchQuery: string;
      limit?: number;
      skip?: number;
    }) => {
      return searchImages({
        query: params.searchQuery,
        limit: params.limit ?? LIMIT,
        skip: params.skip ?? 0,
      });
    },
    onSuccess: (data) => {
      setAllResults(data.results);
      setHasMore(data.has_more);
      setCurrentSkip(data.skip + data.results.length);
    },
  });

  useEffect(() => {
    if (initializedFromUrlRef.current) return;
    const initialQuery = (
      searchParams?.get("q") ??
      (typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("q")
        : null)
    )?.trim();
    if (!initialQuery) return;
    initializedFromUrlRef.current = true;
    setQuery(initialQuery);
    setActiveQuery(initialQuery);
    searchMutation.mutate({ searchQuery: initialQuery, limit: LIMIT, skip: 0 });
  }, [searchParams, searchMutation.mutate]);

  // Periodic refresh - update first page results without losing loaded pages
  useEffect(() => {
    if (!activeQuery) return;

    const intervalId = setInterval(() => {
      const refreshLimit = Math.min(Math.max(currentSkip, LIMIT), 100);
      searchMutation.mutate({
        searchQuery: activeQuery,
        limit: refreshLimit,
        skip: 0,
      });
    }, MINIO_URL_REFRESH_INTERVAL_MS);

    return () => clearInterval(intervalId);
  }, [activeQuery, currentSkip, searchMutation.mutate]);

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (trimmedQuery) {
      setAllResults([]);
      setHasMore(false);
      setCurrentSkip(0);
      setActiveQuery(trimmedQuery);
      searchMutation.mutate({
        searchQuery: trimmedQuery,
        limit: LIMIT,
        skip: 0,
      });
    }
  };

  const loadMoreResults = async () => {
    if (!activeQuery || isLoadingMore || !hasMore) return;

    setIsLoadingMore(true);
    try {
      const data = await searchImages({
        query: activeQuery,
        limit: LIMIT,
        skip: currentSkip,
      });
      setAllResults((prev) => [...prev, ...data.results]);
      setHasMore(data.has_more);
      setCurrentSkip(data.skip + data.results.length);
    } catch (error) {
      console.error("Failed to load more results:", error);
    } finally {
      setIsLoadingMore(false);
    }
  };

  return (
    <div className="page-shell">
      <div className="container-shell py-10 md:py-14">
        <header className="page-enter mb-6 flex flex-wrap items-baseline gap-2 border-b border-[var(--frost)] pb-5">
          <span className="text-sm font-semibold text-[color:var(--blue)]">
            Library
          </span>
          <span aria-hidden="true" className="text-[color:var(--muted)]">
            /
          </span>
          <h1 className="section-heading text-4xl font-medium">Search</h1>
          <span className="text-sm text-[color:var(--silver)]">
            Scenes, objects, captions, and visible text
          </span>
        </header>

        <form onSubmit={handleSearch} className="delayed-enter mb-8 max-w-4xl">
          <div className="frost-panel flex items-center gap-3 rounded-2xl p-2 transition focus-within:border-[var(--frost-strong)]">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-[var(--frost)] bg-[color:var(--surface-soft)] text-[color:var(--blue)]">
              <SearchIcon className="h-5 w-5" />
            </div>
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="A visual memory, object, scene, or mood"
              className="min-w-0 flex-1 bg-transparent py-3 text-base text-[color:var(--near-white)] outline-none placeholder:text-[color:var(--muted)]"
            />
            <button
              type="submit"
              disabled={!query.trim() || searchMutation.isPending}
              className="white-pill h-11 px-5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            >
              {searchMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Search
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
            {(query.trim() || searchMutation.data) && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  searchMutation.reset();
                  setActiveQuery("");
                  setAllResults([]);
                  setHasMore(false);
                  setCurrentSkip(0);
                }}
                className="frost-button h-11 px-5 text-sm font-semibold"
              >
                Clear
              </button>
            )}
          </div>
        </form>

        {searchMutation.isPending && (
          <div className="flex items-center justify-center py-28">
            <Loader2 className="h-8 w-8 animate-spin text-[color:var(--silver)]" />
          </div>
        )}

        {searchMutation.isError && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
            <p className="text-[#ff9bab]">Search failed. Please try again.</p>
          </div>
        )}

        {!searchMutation.data &&
          !searchMutation.isPending &&
          recentQuery.data && (
            <section aria-labelledby="recent-uploads-heading">
              <div className="mb-5 flex items-end justify-between gap-3">
                <div>
                  <h2
                    id="recent-uploads-heading"
                    className="text-xl font-semibold"
                  >
                    Recently uploaded
                  </h2>
                  <p className="mt-1 text-sm text-[color:var(--silver)]">
                    Your newest gallery photos, ready to search.
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
                {recentQuery.data.items.map((item) => (
                  <a
                    key={item.id}
                    href={`/gallery?media=${item.id}`}
                    className="group relative aspect-square overflow-hidden rounded-xl bg-[color:var(--surface-soft)] outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
                  >
                    <Image
                      fill
                      sizes="(max-width: 640px) 50vw, 20vw"
                      unoptimized
                      src={
                        resolveMediaUrl(
                          item.thumbnail_url ?? item.url,
                          item.minio_key,
                          item.id,
                          !item.thumbnail_url,
                        ) ?? ""
                      }
                      alt={item.filename}
                      className="object-cover transition duration-200 group-hover:scale-[1.02]"
                    />
                  </a>
                ))}
              </div>
            </section>
          )}

        {allResults.length === 0 && searchMutation.data && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
            <ImageOff className="mx-auto mb-4 h-10 w-10 text-[color:var(--muted)]" />
            <p className="mb-2 text-[color:var(--near-white)]">
              No results found
            </p>
            <p className="text-sm text-[color:var(--silver)]">
              Try a broader phrase or a visible object.
            </p>
          </div>
        )}

        {allResults.length > 0 && (
          <div className="page-enter">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-[color:var(--silver)]">
                {allResults.length} result
                {allResults.length !== 1 ? "s" : ""} for{" "}
                <span className="text-[color:var(--near-white)]">
                  {activeQuery}
                </span>
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
              {allResults.map((result, index) => (
                <div
                  key={result.media_id}
                  className="group relative aspect-square overflow-hidden rounded-xl bg-[color:var(--surface-soft)] text-left"
                >
                  <Image
                    fill
                    sizes="(max-width: 640px) 50vw, 20vw"
                    unoptimized
                    src={
                      resolveMediaUrl(
                        result.metadata.thumbnail_url ?? result.metadata.url,
                        result.metadata.minio_key,
                        result.media_id,
                        !result.metadata.thumbnail_url,
                      ) ?? ""
                    }
                    alt={result.metadata.filename}
                    className="object-cover transition duration-200 group-hover:scale-[1.02]"
                  />
                  <button
                    type="button"
                    aria-label={`Preview ${result.metadata.filename}`}
                    onClick={() => setViewerIndex(index)}
                    className="absolute inset-0 z-10 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--blue)]"
                  />
                  <div className="pointer-events-none absolute inset-x-2 bottom-2 z-20 flex items-center justify-between gap-2 text-white">
                    <span className="rounded-full bg-black/70 px-2 py-1 text-xs font-semibold">
                      {Math.round(result.similarity * 100)}%
                    </span>
                    <span className="pointer-events-auto">
                      <FeedbackRating
                        label=""
                        onRate={(rating) =>
                          submitSearchRating(result.media_id, rating)
                        }
                      />
                    </span>
                  </div>
                </div>
              ))}
            </div>
            {viewerIndex !== null && allResults[viewerIndex] && (
              <ImagePreviewModal
                media={{
                  ...allResults[viewerIndex].metadata,
                  id: allResults[viewerIndex].media_id,
                }}
                onClose={() => setViewerIndex(null)}
                onPrevious={() =>
                  setViewerIndex((current) =>
                    current === null ? null : current - 1,
                  )
                }
                onNext={() =>
                  setViewerIndex((current) =>
                    current === null ? null : current + 1,
                  )
                }
                hasPrevious={viewerIndex > 0}
                hasNext={viewerIndex < allResults.length - 1}
                onDeleted={(mediaId) => {
                  setAllResults((current) =>
                    current.filter((item) => item.media_id !== mediaId),
                  );
                  setViewerIndex(null);
                }}
              />
            )}

            {hasMore && (
              <div className="mt-8 flex justify-center">
                <button
                  type="button"
                  onClick={loadMoreResults}
                  disabled={isLoadingMore}
                  className="frost-button flex items-center gap-2 px-6 py-3 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isLoadingMore ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    "Load More Results"
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="page-shell" />}>
      <SearchPageContent />
    </Suspense>
  );
}
