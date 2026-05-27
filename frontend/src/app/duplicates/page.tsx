"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import { useState } from "react";
import { api } from "@/lib/api";

interface DuplicatePair {
  duplicate_id: number;
  duplicate_name: string;
  original_id: number;
  original_name: string;
}

interface DuplicatesResponse {
  total: number;
  page: number;
  limit: number;
  items: DuplicatePair[];
}

async function fetchDuplicates(page: number): Promise<DuplicatesResponse> {
  const response = await api.get<DuplicatesResponse>("/api/duplicates", {
    params: { page, limit: 20 },
  });
  return response.data;
}

async function deleteImage(mediaId: number): Promise<void> {
  await api.delete(`/api/image/${mediaId}`);
}

async function clearDuplicateFlag(mediaId: number): Promise<void> {
  await api.post(`/api/image/${mediaId}/keep`);
}

export default function DuplicatesPage() {
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["duplicates", page],
    queryFn: () => fetchDuplicates(page),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteImage,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["duplicates"] }),
  });

  const keepBothMutation = useMutation({
    mutationFn: clearDuplicateFlag,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["duplicates"] }),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-600 dark:text-gray-400">Loading duplicates...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-red-600 dark:text-red-400">Failed to load duplicates.</p>
      </div>
    );
  }

  const totalPages = data ? Math.ceil(data.total / data.limit) : 1;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          Near-Duplicate Images
        </h1>
        <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
          {data?.total ?? 0} near-duplicate pairs found
        </p>
      </div>

      {data?.items.length === 0 ? (
        <div className="text-center py-16 text-gray-500 dark:text-gray-400">
          <p className="text-lg">No near-duplicates found.</p>
          <p className="text-sm mt-2">
            Upload more images to detect similar pairs.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {data?.items.map((pair) => (
            <div
              key={pair.duplicate_id}
              className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4"
            >
              <div className="grid grid-cols-2 gap-4">
                {/* Original */}
                <div className="space-y-2">
                  <p className="text-xs text-gray-600 dark:text-gray-500 uppercase tracking-wide">
                    Original
                  </p>
                  <div className="bg-gray-100 dark:bg-gray-800 rounded-lg aspect-square flex items-center justify-center overflow-hidden">
                    <Image
                      src={`/api/image/${pair.original_id}/thumb`}
                      alt={pair.original_name}
                      width={200}
                      height={200}
                      unoptimized
                      className="object-cover w-full h-full"
                      onError={(e) => {
                        (e.target as HTMLImageElement).src = "/placeholder.svg";
                      }}
                    />
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400 truncate">
                    {pair.original_name}
                  </p>
                </div>

                {/* Duplicate */}
                <div className="space-y-2">
                  <p className="text-xs text-gray-600 dark:text-gray-500 uppercase tracking-wide">
                    Near-duplicate
                  </p>
                  <div className="bg-gray-100 dark:bg-gray-800 rounded-lg aspect-square flex items-center justify-center overflow-hidden">
                    <Image
                      src={`/api/image/${pair.duplicate_id}/thumb`}
                      alt={pair.duplicate_name}
                      width={200}
                      height={200}
                      unoptimized
                      className="object-cover w-full h-full"
                      onError={(e) => {
                        (e.target as HTMLImageElement).src = "/placeholder.svg";
                      }}
                    />
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400 truncate">
                    {pair.duplicate_name}
                  </p>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-800">
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(pair.duplicate_id)}
                  disabled={deleteMutation.isPending}
                  className="flex-1 px-3 py-2 bg-red-100 dark:bg-red-900/40 hover:bg-red-200 dark:hover:bg-red-900/60 text-red-700 dark:text-red-300 text-sm rounded-lg transition-colors disabled:opacity-50"
                >
                  Delete duplicate
                </button>
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(pair.original_id)}
                  disabled={deleteMutation.isPending}
                  className="flex-1 px-3 py-2 bg-red-100 dark:bg-red-900/40 hover:bg-red-200 dark:hover:bg-red-900/60 text-red-700 dark:text-red-300 text-sm rounded-lg transition-colors disabled:opacity-50"
                >
                  Delete original
                </button>
                <button
                  type="button"
                  onClick={() => keepBothMutation.mutate(pair.duplicate_id)}
                  disabled={keepBothMutation.isPending}
                  className="flex-1 px-3 py-2 bg-gray-200 dark:bg-gray-800 hover:bg-gray-300 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-300 text-sm rounded-lg transition-colors disabled:opacity-50"
                >
                  Keep both
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-8">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-800 rounded-lg text-sm disabled:opacity-40 text-gray-900 dark:text-gray-300"
          >
            Previous
          </button>
          <span className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-800 rounded-lg text-sm disabled:opacity-40 text-gray-900 dark:text-gray-300"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
