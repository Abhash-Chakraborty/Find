"use client";

import { useQuery } from "@tanstack/react-query";
import { getClusters } from "@/lib/api";
import { Loader2, Grid3x3 } from "lucide-react";
import Image from "next/image";

export default function ClustersPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["clusters"],
    queryFn: getClusters,
  });

  return (
    <div className="min-h-screen bg-white">
      <div className="max-w-7xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-4xl font-light mb-3 text-black">Clusters</h1>
          <p className="text-gray-500 text-sm">
            Automatically grouped similar images
          </p>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="w-8 h-8 animate-spin text-gray-300" />
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="text-center py-32">
            <p className="text-gray-400">Failed to load clusters</p>
          </div>
        )}

        {/* Empty State */}
        {data && data.clusters.length === 0 && (
          <div className="text-center py-32">
            <Grid3x3 className="w-16 h-16 mx-auto mb-4 text-gray-200" />
            <p className="text-gray-400 mb-2">No clusters found</p>
            <p className="text-gray-300 text-sm">
              Clusters are created automatically after uploading multiple images
            </p>
          </div>
        )}

        {/* Clusters Grid */}
        {data && data.clusters.length > 0 && (
          <div className="space-y-8">
            {data.clusters.map((cluster) => (
              <div
                key={cluster.id}
                className="border-b border-gray-100 pb-8 last:border-0"
              >
                {/* Cluster Header */}
                <div className="mb-4">
                  <div className="flex items-center gap-3 mb-2">
                    <h2 className="text-lg font-medium text-black">
                      Cluster {cluster.id}
                    </h2>
                    <span className="px-2 py-1 bg-gray-100 text-gray-600 text-xs font-medium rounded-sm">
                      {cluster.member_count}{" "}
                      {cluster.member_count === 1 ? "image" : "images"}
                    </span>
                  </div>
                  {cluster.label && (
                    <p className="text-sm text-gray-500">{cluster.label}</p>
                  )}
                  {cluster.description && (
                    <p className="text-sm text-gray-400 mt-1">
                      {cluster.description}
                    </p>
                  )}
                </div>

                {/* Sample Images */}
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-3">
                  {cluster.samples.map((sample) => (
                    <div
                      key={sample.id}
                      className="aspect-square bg-gray-50 rounded-sm overflow-hidden border border-gray-100 hover:border-gray-300 transition-all group"
                    >
                      {sample.url && (
                        <Image
                          src={sample.url}
                          alt={sample.filename}
                          width={200}
                          height={200}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                          unoptimized
                        />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Stats */}
        {data && data.clusters.length > 0 && (
          <div className="mt-12 pt-8 border-t border-gray-100">
            <div className="flex gap-8 text-sm">
              <div>
                <span className="text-gray-400">Total Clusters:</span>{" "}
                <span className="font-medium text-black">{data.total}</span>
              </div>
              <div>
                <span className="text-gray-400">Total Images:</span>{" "}
                <span className="font-medium text-black">
                  {data.clusters.reduce((sum, c) => sum + c.member_count, 0)}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
