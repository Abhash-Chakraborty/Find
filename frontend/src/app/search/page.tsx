"use client";

import { useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  ImageOff,
  Loader2,
  Search as SearchIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { FeedbackRating } from "@/components/feedback-rating";
import { ImagePreviewModal } from "@/components/image-preview-modal";
import { TimelineMediaView } from "@/components/timeline-media-view";
import { type SearchResult, searchImages, submitSearchRating } from "@/lib/api";
import { MINIO_URL_REFRESH_INTERVAL_MS, resolveMediaUrl } from "@/lib/media";

const examples = [
  "sunset over mountains",
  "people smiling",
  "documents with text",
  "street photography at night",
];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [allResults, setAllResults] = useState<SearchResult[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [currentSkip, setCurrentSkip] = useState(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const clearedRef = useRef(false);

  const LIMIT = 24;

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
      clearedRef.current = false;
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
        <div className="page-enter mx-auto mb-10 max-w-3xl text-center">
          <h1 className="section-heading mb-4 text-5xl font-medium md:text-6xl">
            Search
          </h1>
          <p className="muted-copy text-sm leading-6">
            Describe what you remember and Find will surface the matching
            images.
          </p>
        </div>

        <form
          onSubmit={handleSearch}
          className="delayed-enter mx-auto mb-10 max-w-3xl"
        >
          <div className="frost-panel flex items-center gap-3 rounded-3xl p-2 transition focus-within:border-[var(--frost-strong)]">
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
                  clearedRef.current = true;
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

          <div className="mt-5 flex flex-wrap justify-center gap-2">
            {examples.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  clearedRef.current = false;
                  setQuery(example);
                  setAllResults([]);
                  setHasMore(false);
                  setCurrentSkip(0);
                  setActiveQuery(example);
                  searchMutation.mutate({
                    searchQuery: example,
                    limit: LIMIT,
                    skip: 0,
                  });
                }}
                className="frost-button px-3 py-1.5 text-xs text-[color:var(--silver)]"
              >
                {example}
              </button>
            ))}
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

        {!searchMutation.data && !searchMutation.isPending && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
            <SearchIcon className="mx-auto mb-4 h-10 w-10 text-[color:var(--muted)]" />
            <p className="text-sm text-[color:var(--silver)]">
              Start with a place, subject, color, text, or moment.
            </p>
          </div>
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

            <TimelineMediaView
              items={allResults}
              getId={(result) => result.media_id}
              getDate={(result) => result.metadata.created_at}
              getWidth={(result) => result.metadata.width}
              getHeight={(result) => result.metadata.height}
              getThumbnailUrl={(result) =>
                resolveMediaUrl(
                  result.metadata.thumbnail_url ?? result.metadata.url,
                  result.metadata.minio_key,
                  result.media_id,
                  !result.metadata.thumbnail_url,
                )
              }
              getOriginalUrl={(result) =>
                `/api/image/${result.media_id}/original`
              }
              getAlt={(result) => result.metadata.filename}
              getOpenLabel={(result) => `Preview ${result.metadata.filename}`}
              renderItemActions={(result) => (
                <div className="flex items-center gap-2 text-white">
                  <span className="rounded-full bg-black/70 px-2 py-1 text-xs font-semibold">
                    {Math.round(result.similarity * 100)}%
                  </span>
                  <FeedbackRating
                    label=""
                    onRate={(rating) =>
                      submitSearchRating(result.media_id, rating)
                    }
                  />
                </div>
              )}
              renderViewer={({ items, index, onIndexChange, onClose }) => {
                const result = items[index];
                if (!result) return null;
                return (
                  <ImagePreviewModal
                    media={{
                      ...result.metadata,
                      id: result.media_id,
                    }}
                    onClose={onClose}
                    onPrevious={() => onIndexChange(index - 1)}
                    onNext={() => onIndexChange(index + 1)}
                    hasPrevious={index > 0}
                    hasNext={index < items.length - 1}
                    onDeleted={(mediaId) => {
                      setAllResults((current) =>
                        current.filter((item) => item.media_id !== mediaId),
                      );
                      onClose();
                    }}
                  />
                );
              }}
            />

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
