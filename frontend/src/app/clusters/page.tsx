"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Grid3x3,
  ImageOff,
  Loader2,
  Play,
  RefreshCw,
  X,
} from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  ImagePreviewModal,
  type PreviewMedia,
} from "@/components/image-preview-modal";
import {
  type ClusterDetail,
  type ClustersResponse,
  extractErrorMessage,
  getClusterDetail,
  getClusters,
  getGallery,
  getJobStatus,
  triggerClustering,
  updateCluster,
} from "@/lib/api";
import {
  MINIO_URL_REFRESH_INTERVAL_MS,
  MINIO_URL_STALE_TIME_MS,
  resolveMediaUrl,
} from "@/lib/media";

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

function getClusterDisplayName(cluster: {
  id: number;
  label?: string | null;
  description?: string | null;
}) {
  return (
    cluster.label?.trim() ||
    cluster.description?.trim() ||
    `Cluster ${cluster.id}`
  );
}

export default function ClustersPage() {
  const queryClient = useQueryClient();
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(
    null,
  );
  const [previewMedia, setPreviewMedia] = useState<PreviewMedia | null>(null);
  const [clusterJobId, setClusterJobId] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");
  const [clusterLabelDraft, setClusterLabelDraft] = useState("");
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["clusters"],
    queryFn: getClusters,
    refetchInterval: clusterJobId ? 4000 : 10000,
    staleTime: MINIO_URL_STALE_TIME_MS,
  });

  const selectedClusterQuery = useQuery({
    queryKey: ["cluster-detail", selectedClusterId],
    queryFn: () => getClusterDetail(selectedClusterId as number),
    enabled: selectedClusterId !== null,
    staleTime: MINIO_URL_STALE_TIME_MS,
    refetchInterval: MINIO_URL_REFRESH_INTERVAL_MS,
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

  const indexedQuery = useQuery({
    queryKey: ["indexed-stats"],
    queryFn: () => getGallery({ status: "indexed", limit: 1 }),
    refetchInterval: 10000,
  });

  useEffect(() => {
    setClusterLabelDraft(
      selectedClusterQuery.data?.label ??
        selectedClusterQuery.data?.description ??
        "",
    );
  }, [
    selectedClusterQuery.data?.label,
    selectedClusterQuery.data?.description,
  ]);

  useEffect(() => {
    if (!clusterJobId || !clusterJobQuery.data) {
      return;
    }

    if (clusterJobQuery.data.status === "finished") {
      const result = clusterJobQuery.data.result as
        | { message?: string }
        | undefined;
      const message = result?.message || "Clustering completed successfully";

      if (message.includes("Not enough")) {
        toast.info(message);
      } else if (message.toLowerCase().includes("no stable")) {
        toast.info(message);
      } else {
        toast.success(message);
      }
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
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Failed to start clustering"));
    },
  });

  const updateClusterMutation = useMutation({
    mutationFn: ({ clusterId, label }: { clusterId: number; label: string }) =>
      updateCluster(clusterId, { label }),
    onSuccess: (cluster, variables) => {
      const nextLabel = cluster.label?.trim() || null;

      toast.success("Cluster name updated");
      setClusterLabelDraft(nextLabel ?? "");
      queryClient.setQueryData<ClustersResponse>(["clusters"], (current) => {
        if (!current) {
          return current;
        }

        return {
          ...current,
          clusters: current.clusters.map((item) =>
            item.id === variables.clusterId
              ? {
                  ...item,
                  label: nextLabel,
                  description: cluster.description,
                }
              : item,
          ),
        };
      });
      queryClient.setQueryData<ClusterDetail>(
        ["cluster-detail", variables.clusterId],
        (current) =>
          current
            ? {
                ...current,
                label: nextLabel,
                description: cluster.description,
              }
            : current,
      );
      queryClient.invalidateQueries({ queryKey: ["clusters"] });
      queryClient.invalidateQueries({
        queryKey: ["cluster-detail", variables.clusterId],
      });
      queryClient.invalidateQueries({ queryKey: ["image-detail"] });
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Failed to rename cluster"));
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
  const isClusterActionBusy =
    clusterMutation.isPending || clusterJobQuery.isFetching || isJobActive;
  const minClusterSize = data?.min_cluster_size ?? 2;
  const effectiveMinClusterSize = Math.max(minClusterSize, 1);
  const indexedImageCount = indexedQuery.data?.total ?? 0;
  const hasEnoughIndexedImages =
    indexedQuery.isSuccess &&
    indexedImageCount > 0 &&
    indexedImageCount >= effectiveMinClusterSize;
  const isClusterButtonDisabled =
    isClusterActionBusy || !hasEnoughIndexedImages;
  const clusteringUnavailableMessage =
    indexedQuery.isSuccess && !hasEnoughIndexedImages
      ? `Need at least ${effectiveMinClusterSize} indexed images to cluster. Found ${indexedImageCount}.`
      : null;

  const emptyStateVariant = useMemo(() => {
    if (!indexedQuery.isSuccess) return "loading";
    if (indexedImageCount === 0) return "no-indexed-images";
    if (indexedImageCount < effectiveMinClusterSize) return "not-enough-images";
    return "no-stable-clusters";
  }, [indexedQuery.isSuccess, indexedImageCount, effectiveMinClusterSize]);

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
              disabled={isClusterButtonDisabled}
              className="white-pill px-5 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
              title={clusteringUnavailableMessage ?? undefined}
            >
              {isClusterActionBusy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {isClusterActionBusy ? "Clustering..." : "Re-cluster"}
            </button>
          </div>
        </div>

        {activeJobStatus && (
          <div className="mb-8 flex justify-center">
            <div className="frost-panel inline-flex flex-wrap items-center justify-center gap-3 rounded-full px-5 py-3">
              {isJobActive && (
                <Loader2 className="h-4 w-4 animate-spin text-[color:var(--blue)]" />
              )}
              <span className={getJobStatusClass(activeJobStatus)}>
                {formatJobStatus(activeJobStatus)}
              </span>
              {clusterJobQuery.data?.job_id && (
                <span className="text-xs text-[color:var(--silver)]">
                  ID {clusterJobQuery.data.job_id.slice(0, 8)}
                </span>
              )}
            </div>
          </div>
        )}

        {isLoading && (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="h-8 w-8 animate-spin text-[color:var(--silver)]" />
          </div>
        )}

        {error && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
            <p className="text-[#ff9bab]">Failed to load clusters</p>
          </div>
        )}

        {data && data.clusters.length === 0 && (
          <>
            {emptyStateVariant === "loading" && (
              <div className="flex items-center justify-center py-32">
                <Loader2 className="h-8 w-8 animate-spin text-[color:var(--silver)]" />
              </div>
            )}

            {emptyStateVariant === "no-indexed-images" && (
              <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
                <ImageOff className="mx-auto mb-4 h-10 w-10 text-[color:var(--muted)]" />
                <p className="mb-1 font-medium text-[color:var(--near-white)]">
                  No indexed images yet
                </p>
                <p className="text-sm text-[color:var(--silver)]">
                  Upload and index images before clustering.
                </p>
              </div>
            )}

            {emptyStateVariant === "not-enough-images" && (
              <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
                <ImageOff className="mx-auto mb-4 h-10 w-10 text-[color:var(--muted)]" />
                <p className="mb-1 font-medium text-[color:var(--near-white)]">
                  Not enough indexed images
                </p>
                <p className="mb-6 text-sm text-[color:var(--silver)]">
                  Need at least {minClusterSize} indexed images before
                  clustering. Found {indexedImageCount}.
                </p>
                <div
                  className="mx-auto mb-2 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-[color:var(--frost)]"
                  role="progressbar"
                  aria-valuenow={indexedImageCount}
                  aria-valuemin={0}
                  aria-valuemax={minClusterSize}
                  aria-label={`${indexedImageCount} of ${minClusterSize} images indexed`}
                >
                  <div
                    className="h-full rounded-full bg-[color:var(--blue)] transition-all duration-500"
                    style={{
                      width: `${Math.min((indexedImageCount / minClusterSize) * 100, 100)}%`,
                    }}
                  />
                </div>
                <p className="text-xs text-[color:var(--muted)]">
                  {indexedImageCount} / {minClusterSize} indexed
                </p>
              </div>
            )}

            {emptyStateVariant === "no-stable-clusters" && (
              <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center">
                <Grid3x3 className="mx-auto mb-4 h-10 w-10 text-[color:var(--muted)]" />
                <p className="mb-1 font-medium text-[color:var(--near-white)]">
                  No stable clusters found
                </p>
                <p className="mb-6 text-sm text-[color:var(--silver)]">
                  Try indexing more visually similar images.
                </p>
                <button
                  type="button"
                  onClick={() => clusterMutation.mutate()}
                  disabled={isClusterActionBusy}
                  className="white-pill px-5 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isClusterActionBusy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {isClusterActionBusy ? "Clustering..." : "Run clustering"}
                </button>
              </div>
            )}
          </>
        )}

        {data && data.clusters.length > 0 && (
          <div className="page-enter">
            <div className="mb-8 grid gap-3 sm:grid-cols-2">
              <div className="frost-panel rounded-2xl p-4">
                <p className="text-xs uppercase text-[color:var(--muted)]">
                  Total clusters
                </p>
                <p className="mt-2 text-3xl font-light text-[color:var(--near-white)]">
                  {totals.totalClusters}
                </p>
              </div>
              <div className="frost-panel rounded-2xl p-4">
                <p className="text-xs uppercase text-[color:var(--muted)]">
                  Clustered images
                </p>
                <p className="mt-2 text-3xl font-light text-[color:var(--near-white)]">
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
                        <h2 className="text-lg font-medium text-[color:var(--near-white)]">
                          {getClusterDisplayName(cluster)}
                        </h2>
                        <span className="accent-badge status-default">
                          {cluster.member_count}{" "}
                          {cluster.member_count === 1 ? "image" : "images"}
                        </span>
                      </div>
                      {(cluster.label?.trim() ||
                        cluster.description?.trim()) && (
                        <p className="text-xs uppercase text-[color:var(--muted)]">
                          Cluster {cluster.id}
                        </p>
                      )}
                      {cluster.description &&
                        cluster.label?.trim() &&
                        cluster.description.trim() !== cluster.label.trim() && (
                          <p className="mt-1 line-clamp-2 text-sm leading-6 text-[color:var(--muted)]">
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
                      const imageSrc = resolveMediaUrl(
                        sample.thumbnail_url ?? sample.url,
                        null,
                        sample.id,
                        !sample.thumbnail_url,
                      );

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
                          className="group relative aspect-square overflow-hidden rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)]"
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
                            <div className="flex h-full w-full items-center justify-center text-[color:var(--muted)]">
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
          <div className="frost-panel page-enter relative max-h-[90dvh] w-full max-w-6xl overflow-hidden rounded-3xl bg-[color:var(--void)]">
            <button
              type="button"
              onClick={() => {
                setSelectedClusterId(null);
                setFilterText("");
                setClusterLabelDraft(
                  selectedClusterQuery.data?.label ??
                    selectedClusterQuery.data?.description ??
                    "",
                );
              }}
              className="icon-button absolute right-4 top-4 z-20 bg-[color:var(--overlay)] text-white backdrop-blur-md"
              aria-label="Close cluster detail"
            >
              <X className="h-4 w-4" />
            </button>

            <div className="border-b border-[var(--frost)] px-6 py-5">
              <h2 className="text-xl font-medium text-[color:var(--near-white)]">
                {selectedClusterQuery.data
                  ? getClusterDisplayName(selectedClusterQuery.data)
                  : `Cluster ${selectedClusterId}`}
              </h2>
              {selectedClusterQuery.data &&
                (selectedClusterQuery.data.label?.trim() ||
                  selectedClusterQuery.data.description?.trim()) && (
                  <p className="mt-1 text-xs uppercase text-[color:var(--muted)]">
                    Cluster {selectedClusterId}
                  </p>
                )}
              <p className="mt-1 text-sm text-[color:var(--silver)]">
                Images grouped by visual and semantic similarity.
              </p>
            </div>

            <div className="max-h-[calc(90dvh-88px)] overflow-y-auto p-6">
              {selectedClusterQuery.isLoading && (
                <div className="flex items-center justify-center py-24">
                  <Loader2 className="h-8 w-8 animate-spin text-[color:var(--silver)]" />
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
                    {selectedClusterQuery.data.description &&
                      selectedClusterQuery.data.label?.trim() &&
                      selectedClusterQuery.data.description.trim() !==
                        selectedClusterQuery.data.label.trim() && (
                        <span className="text-sm text-[color:var(--muted)]">
                          {selectedClusterQuery.data.description}
                        </span>
                      )}
                  </div>
                  <form
                    className="mb-6 flex flex-col gap-2 sm:flex-row"
                    onSubmit={(event) => {
                      event.preventDefault();
                      updateClusterMutation.mutate({
                        clusterId: selectedClusterQuery.data.id,
                        label: clusterLabelDraft,
                      });
                    }}
                  >
                    <input
                      type="text"
                      value={clusterLabelDraft}
                      onChange={(event) =>
                        setClusterLabelDraft(event.target.value)
                      }
                      placeholder={`Cluster ${selectedClusterQuery.data.id}`}
                      aria-label="Cluster name"
                      maxLength={255}
                      className="min-w-0 flex-1 rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-4 py-3 text-sm text-[color:var(--near-white)] outline-none transition focus:border-[#3b9eff]"
                    />
                    <button
                      type="submit"
                      disabled={updateClusterMutation.isPending}
                      className="white-pill justify-center px-4 py-3 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {updateClusterMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Check className="h-4 w-4" />
                      )}
                      Save name
                    </button>
                  </form>
                  <div className="mb-6">
                    <input
                      type="text"
                      placeholder="Filter by filename..."
                      aria-label="Filter cluster members by filename"
                      value={filterText}
                      onChange={(e) => setFilterText(e.target.value)}
                      className="w-full rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-4 py-3 text-sm text-[color:var(--near-white)] outline-none transition focus:border-[#3b9eff]"
                    />
                  </div>
                  {filteredMembers.length === 0 && (
                    <div className="py-12 text-center text-[color:var(--silver)]">
                      No matching members found.
                    </div>
                  )}

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {filteredMembers.map((member) => {
                      const imageSrc = resolveMediaUrl(
                        member.thumbnail_url ?? member.url,
                        null,
                        member.id,
                        !member.thumbnail_url,
                      );

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
                          <div className="relative aspect-[4/3] bg-[color:var(--surface-soft)]">
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
                              <div className="flex h-full w-full items-center justify-center text-[color:var(--muted)]">
                                <ImageOff className="h-6 w-6" />
                              </div>
                            )}
                          </div>
                          <div className="space-y-2 p-4">
                            <p className="truncate text-sm font-medium text-[color:var(--near-white)]">
                              {member.filename}
                            </p>
                            {member.caption && (
                              <p className="line-clamp-2 text-sm leading-6 text-[color:var(--silver)]">
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
