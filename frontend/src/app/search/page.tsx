"use client";

import { useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  ImageOff,
  Loader2,
  Search as SearchIcon,
} from "lucide-react";
import Image from "next/image";
import { useCallback, useMemo, useRef, useState } from "react";
import { ImagePreviewModal } from "@/components/image-preview-modal";
import { StatusIndicator } from "@/components/status-indicator";
import { searchImages } from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";

const examples = [
  "sunset over mountains",
  "people smiling",
  "documents with text",
  "street photography at night",
];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [selectedMediaId, setSelectedMediaId] = useState<number | null>(null);
  const clearedRef = useRef(false);

  const searchMutation = useMutation({
    mutationFn: (searchQuery: string) =>
      searchImages({ query: searchQuery, limit: 24 }),
  });

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    if (query.trim()) {
      clearedRef.current = false;
      setSelectedMediaId(null);
      searchMutation.mutate(query.trim());
    }
  };

  const results = searchMutation.data?.results ?? [];
  const selectedIndex = useMemo(() => {
    if (selectedMediaId === null) {
      return -1;
    }
    return results.findIndex((result) => result.media_id === selectedMediaId);
  }, [results, selectedMediaId]);
  const selectedMedia = selectedIndex >= 0 ? results[selectedIndex] : null;

  const goToAdjacent = useCallback(
    (direction: -1 | 1) => {
      if (selectedIndex < 0) {
        return;
      }
      const next = results[selectedIndex + direction];
      if (next) {
        setSelectedMediaId(next.media_id);
      }
    },
    [results, selectedIndex],
  );

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
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-[var(--frost)] bg-white/[0.04] text-[#3b9eff]">
              <SearchIcon className="h-5 w-5" />
            </div>
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="A visual memory, object, scene, or mood"
              className="min-w-0 flex-1 bg-transparent py-3 text-base text-[#f0f0f0] outline-none placeholder:text-[#5f6568]"
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
                  setSelectedMediaId(null);
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
                  setSelectedMediaId(null);
                  searchMutation.mutate(example);
                }}
                className="frost-button px-3 py-1.5 text-xs text-[#a1a4a5]"
              >
                {example}
              </button>
            ))}
          </div>
        </form>

        {searchMutation.isPending && (
          <div className="flex items-center justify-center py-28">
            <Loader2 className="h-8 w-8 animate-spin text-[#a1a4a5]" />
          </div>
        )}

        {searchMutation.isError && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
            <p className="text-[#ff9bab]">Search failed. Please try again.</p>
          </div>
        )}

        {!searchMutation.data && !searchMutation.isPending && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
            <SearchIcon className="mx-auto mb-4 h-10 w-10 text-[#5f6568]" />
            <p className="text-sm text-[#a1a4a5]">
              Start with a place, subject, color, text, or moment.
            </p>
          </div>
        )}

        {searchMutation.data && searchMutation.data.results.length === 0 && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
            <ImageOff className="mx-auto mb-4 h-10 w-10 text-[#5f6568]" />
            <p className="mb-2 text-[#f0f0f0]">No results found</p>
            <p className="text-sm text-[#a1a4a5]">
              Try a broader phrase or a visible object.
            </p>
          </div>
        )}

        {searchMutation.data && searchMutation.data.results.length > 0 && (
          <div className="page-enter">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-[#a1a4a5]">
                {searchMutation.data.results.length} result
                {searchMutation.data.results.length !== 1 ? "s" : ""} for{" "}
                <span className="text-[#f0f0f0]">
                  {searchMutation.data.query}
                </span>
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">
              {searchMutation.data.results.map((result) => {
                const imageSrc = resolveMediaUrl(
                  result.metadata.url,
                  result.metadata.minio_key,
                );

                return (
                  <button
                    type="button"
                    key={result.media_id}
                    onClick={() => setSelectedMediaId(result.media_id)}
                    className="frost-panel card-hover group relative overflow-hidden rounded-2xl text-left"
                    aria-label={`Preview ${result.metadata.filename}`}
                  >
                    <div className="relative aspect-square overflow-hidden bg-white/[0.025]">
                      {imageSrc ? (
                        <Image
                          src={imageSrc}
                          alt={result.metadata.filename}
                          fill
                          className="object-cover transition duration-500 group-hover:scale-[1.035]"
                          sizes="(max-width: 768px) 50vw, (max-width: 1200px) 25vw, 16vw"
                          unoptimized
                        />
                      ) : (
                        <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-[#5f6568]">
                          <ImageOff className="h-7 w-7" />
                          <span className="text-xs">No preview</span>
                        </div>
                      )}
                      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent opacity-70 transition-opacity group-hover:opacity-95" />
                      <span className="absolute right-3 top-3 rounded-full border border-[var(--frost)] bg-black/[0.55] px-2.5 py-1 text-xs font-medium text-[#f0f0f0] backdrop-blur-md">
                        {Math.round(result.similarity * 100)}%
                      </span>
                      <StatusIndicator
                        status={result.metadata.status}
                        className="absolute bottom-3 right-3"
                      />
                    </div>

                    <div className="space-y-3 p-3">
                      <p className="truncate text-xs font-medium text-[#f0f0f0]">
                        {result.metadata.filename}
                      </p>
                      {result.metadata.caption && (
                        <p className="line-clamp-2 text-xs leading-5 text-[#a1a4a5]">
                          {result.metadata.caption}
                        </p>
                      )}
                      <div className="flex flex-wrap items-center gap-2">
                        {typeof result.metadata.cluster_id === "number" && (
                          <span className="accent-badge status-default">
                            Cluster {result.metadata.cluster_id}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {selectedMedia && (
        <ImagePreviewModal
          media={{
            ...selectedMedia.metadata,
            id: selectedMedia.media_id,
          }}
          onClose={() => setSelectedMediaId(null)}
          onPrevious={() => goToAdjacent(-1)}
          onNext={() => goToAdjacent(1)}
          hasPrevious={selectedIndex > 0}
          hasNext={selectedIndex >= 0 && selectedIndex < results.length - 1}
          onDeleted={(mediaId) => {
            if (selectedMediaId === mediaId) {
              setSelectedMediaId(null);
            }
          }}
        />
      )}
    </div>
  );
}
