"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Grid3x3, ImageOff, Loader2, Play, RefreshCw, X } from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  ImagePreviewModal,
  type PreviewMedia,
} from "@/components/image-preview-modal";
import {
  getClusterDetail,
  getClusters,
  getJobStatus,
  triggerClustering,
} from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";

function formatJobStatus(status?: string) {
  switch (status) {
    case "queued":
      return "Queued";
    case "started":
      return "Running";
    case "finished":
      return "Finished";
    case "failed":
      return "Failed";
    default:
      return "Idle";
  }
}

function getJobStatusClass(status?: string) {
  switch (status) {
    case "finished":
      return "accent-badge status-indexed";
    case "failed":
      return "accent-badge status-failed";
    case "queued":
    case "started":
      return "accent-badge status-processing";
    default:
      return "accent-badge status-default";
  }
}

export default function ClustersPage() {
  const queryClient = useQueryClient();
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(
    null,
  );
  const [previewMedia, setPreviewMedia] = useState<PreviewMedia | null>(null);
  const [clusterJobId, setClusterJobId] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["clusters"],
    queryFn: getClusters,
    refetchInterval: clusterJobId ? 4000 : 10000,
  });

  const selectedClusterQuery = useQuery({
    queryKey: ["cluster-detail", selectedClusterId],
    queryFn: () => getClusterDetail(selectedClusterId as number),
    enabled: selectedClusterId !== null,
  });

  const clusterJobQuery = useQuery({
    queryKey: ["cluster-job", clusterJobId],
    queryFn: () => getJobStatus(clusterJobId as string),
    enabled: clusterJobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "finished" || status === "failed" ? false : 2500;
    },
  });

  useEffect(() => {
    if (!clusterJobId || !clusterJobQuery.data) {
      return;
    }

    if (clusterJobQuery.data.status === "finished") {
      toast.success("Clustering finished. The page has been refreshed.");
      queryClient.invalidateQueries({ queryKey: ["clusters"] });
      setClusterJobId(null);
    }

    if (clusterJobQuery.data.status === "failed") {
      toast.error("Clustering failed. Check the worker logs for details.");
      setClusterJobId(null);
    }
  }, [clusterJobId, clusterJobQuery.data, queryClient]);

  const clusterMutation = useMutation({
    mutationFn: triggerClustering,
    onSuccess: (result) => {
      setClusterJobId(result.job_id);
      toast.success(
        result.enqueued
          ? "Clustering job queued"
          : "Clustering is already queued or running",
      );
    },
    onError: () => {
      toast.error("Failed to start clustering");
    },
  });

  const totals = useMemo(() => {
    const totalImages = data?.clusters.reduce(
      (sum, cluster) => sum + cluster.member_count,
      0,
    );

    return {
      totalClusters: data?.total ?? 0,
      totalImages: totalImages ?? 0,
    };
  }, [data]);

  const activeJobStatus = clusterJobQuery.data?.status;
  const isJobActive =
    activeJobStatus === "queued" || activeJobStatus === "started";
  const filteredMembers =
    selectedClusterQuery.data?.members.filter((member) =>
      member.filename.toLowerCase().includes(filterText.toLowerCase()),
    ) ?? [];

  return (
    <div className="page-shell">
      <div className="container-shell py-10 md:py-14">
        <div className="page-enter mb-10 flex flex-col gap-6 border-b border-[var(--frost)] pb-8 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <h1 className="section-heading mb-4 text-5xl font-medium md:text-6xl">
              Clusters
            </h1>
            <p className="muted-copy text-sm leading-6">
              Similar images are grouped into clean, browsable sets as your
              library is indexed.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() =>
                queryClient.invalidateQueries({ queryKey: ["clusters"] })
              }
              className="frost-button px-5 py-2.5 text-sm font-medium"
            >
              <RefreshCw
                className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
              />
              Refresh
            </button>
            <button
              type="button"
              onClick={() => clusterMutation.mutate()}
              disabled={clusterMutation.isPending || clusterJobQuery.isFetching}
              className="white-pill px-5 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            >
              {clusterMutation.isPending || clusterJobQuery.isFetching ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Re-cluster
            </button>
          </div>
        </div>

        {activeJobStatus && (
          <div className="mb-8 flex justify-center">
            <div className="frost-panel inline-flex flex-wrap items-center justify-center gap-3 rounded-full px-5 py-3">
              {isJobActive && (
                <Loader2 className="h-4 w-4 animate-spin text-[#3b9eff]" />
              )}
              <span className={getJobStatusClass(activeJobStatus)}>
                {formatJobStatus(activeJobStatus)}
              </span>
              {clusterJobQuery.data?.job_id && (
                <span className="text-xs text-[#a1a4a5]">
                  ID {clusterJobQuery.data.job_id.slice(0, 8)}
                </span>
              )}
            </div>
          </div>
        )}

        {isLoading && (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="h-8 w-8 animate-spin text-[#a1a4a5]" />
          </div>
        )}

        {error && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
            <p className="text-[#ff9bab]">Failed to load clusters</p>
          </div>
        )}

        {data && data.clusters.length === 0 && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
            <Grid3x3 className="mx-auto mb-4 h-10 w-10 text-[#5f6568]" />
            <p className="mb-2 text-[#f0f0f0]">No clusters yet</p>
            <p className="mb-6 text-sm leading-6 text-[#a1a4a5]">
              Index a few related images, then run clustering.
            </p>
            <button
              type="button"
              onClick={() => clusterMutation.mutate()}
              disabled={clusterMutation.isPending}
              className="white-pill px-5 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              Run clustering
            </button>
          </div>
        )}

        {data && data.clusters.length > 0 && (
          <div className="page-enter">
            <div className="mb-8 grid gap-3 sm:grid-cols-2">
              <div className="frost-panel rounded-2xl p-4">
                <p className="text-xs uppercase text-[#5f6568]">
                  Total clusters
                </p>
                <p className="mt-2 text-3xl font-light text-[#f0f0f0]">
                  {totals.totalClusters}
                </p>
              </div>
              <div className="frost-panel rounded-2xl p-4">
                <p className="text-xs uppercase text-[#5f6568]">
                  Clustered images
                </p>
                <p className="mt-2 text-3xl font-light text-[#f0f0f0]">
                  {totals.totalImages}
                </p>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {data.clusters.map((cluster) => (
                <article
                  key={cluster.id}
                  className="frost-panel card-hover rounded-3xl p-5"
                >
                  <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-medium text-[#f0f0f0]">
                          Cluster {cluster.id}
                        </h2>
                        <span className="accent-badge status-default">
                          {cluster.member_count}{" "}
                          {cluster.member_count === 1 ? "image" : "images"}
                        </span>
                      </div>
                      {cluster.label && (
                        <p className="text-sm text-[#a1a4a5]">
                          {cluster.label}
                        </p>
                      )}
                      {cluster.description && (
                        <p className="mt-1 line-clamp-2 text-sm leading-6 text-[#5f6568]">
                          {cluster.description}
                        </p>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => setSelectedClusterId(cluster.id)}
                      className="frost-button shrink-0 px-4 py-2 text-sm font-medium"
                    >
                      View members
                    </button>
                  </div>

                  <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
                    {cluster.samples.map((sample) => {
                      const imageSrc = resolveMediaUrl(sample.url);

                      return (
                        <button
                          type="button"
                          key={sample.id}
                          onClick={() =>
                            setPreviewMedia({
                              id: sample.id,
                              filename: sample.filename,
                              url: sample.url,
                            })
                          }
                          className="group relative aspect-square overflow-hidden rounded-2xl border border-[var(--frost)] bg-white/[0.025]"
                          aria-label={`Preview ${sample.filename}`}
                        >
                          {imageSrc ? (
                            <Image
                              src={imageSrc}
                              alt={sample.filename}
                              fill
                              className="object-cover transition duration-500 group-hover:scale-[1.05]"
                              sizes="(max-width: 768px) 25vw, 10vw"
                              unoptimized
                            />
                          ) : (
                            <div className="flex h-full w-full items-center justify-center text-[#5f6568]">
                              <ImageOff className="h-5 w-5" />
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </div>

      {selectedClusterId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 px-4 backdrop-blur-xl">
          <div className="frost-panel page-enter relative max-h-[90dvh] w-full max-w-6xl overflow-hidden rounded-3xl bg-black">
            <button
              type="button"
              onClick={() => {
                setSelectedClusterId(null);
                setFilterText("");
              }}
              className="icon-button absolute right-4 top-4 z-20 bg-black/60 backdrop-blur-md"
              aria-label="Close cluster detail"
            >
              <X className="h-4 w-4" />
            </button>

            <div className="border-b border-[var(--frost)] px-6 py-5">
              <h2 className="text-xl font-medium text-[#f0f0f0]">
                Cluster {selectedClusterId}
              </h2>
              <p className="mt-1 text-sm text-[#a1a4a5]">
                Images grouped by visual and semantic similarity.
              </p>
            </div>

            <div className="max-h-[calc(90dvh-88px)] overflow-y-auto p-6">
              {selectedClusterQuery.isLoading && (
                <div className="flex items-center justify-center py-24">
                  <Loader2 className="h-8 w-8 animate-spin text-[#a1a4a5]" />
                </div>
              )}

              {selectedClusterQuery.isError && (
                <div className="py-16 text-center text-[#ff9bab]">
                  Failed to load cluster details.
                </div>
              )}

              {selectedClusterQuery.data && (
                <div>
                  <div className="mb-6 flex flex-wrap items-center gap-3">
                    <span className="accent-badge status-default">
                      {selectedClusterQuery.data.member_count} members
                    </span>
                    {selectedClusterQuery.data.label && (
                      <span className="text-sm text-[#a1a4a5]">
                        {selectedClusterQuery.data.label}
                      </span>
                    )}
                    {selectedClusterQuery.data.description && (
                      <span className="text-sm text-[#5f6568]">
                        {selectedClusterQuery.data.description}
                      </span>
                    )}
                  </div>
                  <div className="mb-6">
                    <input
                      type="text"
                      placeholder="Filter by filename..."
                      aria-label="Filter cluster members by filename"
                      value={filterText}
                      onChange={(e) => setFilterText(e.target.value)}
                      className="w-full rounded-2xl border border-[var(--frost)] bg-white/[0.03] px-4 py-3 text-sm text-[#f0f0f0] outline-none transition focus:border-[#3b9eff]"
                    />
                  </div>
                  {filteredMembers.length === 0 && (
                    <div className="py-12 text-center text-[#a1a4a5]">
                      No matching members found.
                    </div>
                  )}

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {filteredMembers.map((member) => {
                      const imageSrc = resolveMediaUrl(member.url);

                      return (
                        <button
                          type="button"
                          key={member.id}
                          onClick={() =>
                            setPreviewMedia({
                              id: member.id,
                              filename: member.filename,
                              url: member.url,
                              caption: member.caption,
                            })
                          }
                          className="frost-panel card-hover overflow-hidden rounded-3xl text-left"
                          aria-label={`Preview ${member.filename}`}
                        >
                          <div className="relative aspect-[4/3] bg-white/[0.025]">
                            {imageSrc ? (
                              <Image
                                src={imageSrc}
                                alt={member.filename}
                                fill
                                className="object-cover"
                                sizes="(max-width: 768px) 100vw, 33vw"
                                unoptimized
                              />
                            ) : (
                              <div className="flex h-full w-full items-center justify-center text-[#5f6568]">
                                <ImageOff className="h-6 w-6" />
                              </div>
                            )}
                          </div>
                          <div className="space-y-2 p-4">
                            <p className="truncate text-sm font-medium text-[#f0f0f0]">
                              {member.filename}
                            </p>
                            {member.caption && (
                              <p className="line-clamp-2 text-sm leading-6 text-[#a1a4a5]">
                                {member.caption}
                              </p>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {previewMedia && (
        <ImagePreviewModal
          media={previewMedia}
          onClose={() => setPreviewMedia(null)}
          onDeleted={(mediaId) => {
            if (previewMedia.id === mediaId) {
              setPreviewMedia(null);
            }
          }}
        />
      )}
    </div>
  );
}
