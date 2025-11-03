"use client";

import { useCallback, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { searchImages } from "@/lib/api";
import { Search as SearchIcon, Loader2, Sparkles } from "lucide-react";
import Image from "next/image";
import { getStatusBadgeClass } from "@/lib/utils";

export default function SearchPage() {
  const [query, setQuery] = useState("");

  const bucket = process.env.NEXT_PUBLIC_MINIO_BUCKET ?? "images";
  const minioBaseUrl =
    process.env.NEXT_PUBLIC_MINIO_URL ?? "http://localhost:9000";
  const sanitizedBase = useMemo(
    () =>
      minioBaseUrl.endsWith("/") ? minioBaseUrl.slice(0, -1) : minioBaseUrl,
    [minioBaseUrl]
  );
  const buildEncodedUrl = useCallback(
    (objectKey?: string | null) => {
      if (!objectKey) {
        return null;
      }
      const encodedKey = objectKey
        .split("/")
        .map((segment) => encodeURIComponent(segment))
        .join("/");
      return `${sanitizedBase}/${bucket}/${encodedKey}`;
    },
    [bucket, sanitizedBase]
  );

  const searchMutation = useMutation({
    mutationFn: (searchQuery: string) =>
      searchImages({ query: searchQuery, limit: 24 }),
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      searchMutation.mutate(query.trim());
    }
  };

  return (
    <div className="min-h-screen bg-white">
      <div className="max-w-7xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-4xl font-light mb-3 text-black">Search</h1>
          <p className="text-gray-500 text-sm">
            Find images using natural language
          </p>
        </div>

        {/* Search Form */}
        <form onSubmit={handleSearch} className="mb-12">
          <div className="relative max-w-2xl">
            <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-300" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Describe what you're looking for..."
              className="w-full pl-12 pr-4 py-4 border border-gray-200 rounded-sm focus:outline-none focus:border-black transition-colors text-sm"
            />
          </div>

          <div className="flex gap-2 mt-3">
            <span className="text-xs text-gray-400">Try:</span>
            {[
              "sunset over mountains",
              "people smiling",
              "documents with text",
            ].map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example);
                  searchMutation.mutate(example);
                }}
                className="text-xs text-gray-400 hover:text-black transition-colors"
              >
                "{example}"
              </button>
            ))}
          </div>
        </form>

        {/* Loading */}
        {searchMutation.isPending && (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="w-8 h-8 animate-spin text-gray-300" />
          </div>
        )}

        {/* Error */}
        {searchMutation.isError && (
          <div className="text-center py-32">
            <p className="text-gray-400">Search failed. Please try again.</p>
          </div>
        )}

        {/* Empty State */}
        {!searchMutation.data && !searchMutation.isPending && (
          <div className="text-center py-32">
            <Sparkles className="w-16 h-16 mx-auto mb-4 text-gray-200" />
            <p className="text-gray-400 mb-2">Start searching</p>
            <p className="text-gray-300 text-sm">
              Use natural language to find your images
            </p>
          </div>
        )}

        {/* No Results */}
        {searchMutation.data && searchMutation.data.results.length === 0 && (
          <div className="text-center py-32">
            <p className="text-gray-400 mb-2">No results found</p>
            <p className="text-gray-300 text-sm">
              Try a different search query
            </p>
          </div>
        )}

        {/* Results */}
        {searchMutation.data && searchMutation.data.results.length > 0 && (
          <div>
            <p className="text-sm text-gray-400 mb-6">
              Found {searchMutation.data.results.length} result
              {searchMutation.data.results.length !== 1 ? "s" : ""}
            </p>

            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-4">
              {searchMutation.data.results.map((result) => {
                const imageSrc =
                  buildEncodedUrl(result.metadata.minio_key) ??
                  "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";

                return (
                  <div
                    key={result.media_id}
                    className="group relative aspect-square bg-gray-50 rounded-sm overflow-hidden border border-gray-100 hover:border-gray-300 transition-all"
                  >
                    <Image
                      src={imageSrc}
                      alt={result.metadata.filename}
                      fill
                      className="object-cover"
                      sizes="(max-width: 768px) 50vw, (max-width: 1200px) 33vw, 16vw"
                      unoptimized
                    />

                    {/* Similarity Badge */}
                    <div className="absolute top-2 right-2 bg-white/90 backdrop-blur-sm px-2 py-1 rounded-sm">
                      <span className="text-xs font-medium text-black">
                        {Math.round(result.similarity * 100)}%
                      </span>
                    </div>

                    {/* Overlay */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                      <div className="absolute bottom-0 left-0 right-0 p-3">
                        <p className="text-white text-xs font-medium truncate mb-1">
                          {result.metadata.filename}
                        </p>
                        {result.metadata.caption && (
                          <p className="text-white/80 text-xs truncate mb-1">
                            {result.metadata.caption}
                          </p>
                        )}
                        <span
                          className={getStatusBadgeClass(
                            result.metadata.status
                          )}
                        >
                          {result.metadata.status}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
