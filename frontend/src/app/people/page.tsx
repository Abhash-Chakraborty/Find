"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Loader2,
  Pencil,
  Play,
  RefreshCw,
  Users,
  X,
} from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ImagePreviewModal,
  type PreviewMedia,
} from "@/components/image-preview-modal";
import { FeedbackActions } from "@/components/person-feedback-actions";
import {
  getPeople,
  getPersonImages,
  type PersonItem,
  submitPersonFeedbackWrongPerson,
  triggerFaceClustering,
  updatePersonName,
} from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";

// ─── Person Card Component ────────────────────────────────────────────────────

function PersonCard({
  person,
  onClick,
  onNameSaved,
}: {
  person: PersonItem;
  onClick: () => void;
  onNameSaved: () => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [nameInput, setNameInput] = useState(person.name ?? "");

  // Sync input state if name changes or editing gets cancelled
  useEffect(() => {
    if (!isEditing) {
      setNameInput(person.name ?? "");
    }
  }, [person.name, isEditing]);

  const submitName = () => {
    const trimmed = nameInput.trim();
    if (!trimmed) {
      toast.error("Name cannot be empty");
      return;
    }
    nameMutation.mutate(trimmed);
  };

  const nameMutation = useMutation({
    mutationFn: (name: string) => updatePersonName(person.id, name),
    onSuccess: () => {
      toast.success("Name saved!");
      setIsEditing(false);
      onNameSaved();
    },
    onError: () => {
      toast.error("Failed to save name");
    },
  });

  return (
    <article className="frost-panel card-hover relative flex h-full flex-col rounded-3xl border border-[var(--frost)] bg-[hsl(var(--background))] p-4 text-[hsl(var(--foreground))] transition hover:border-[var(--frost-strong)]">
      <button
        type="button"
        className="absolute inset-0 z-0 rounded-3xl"
        onClick={onClick}
        aria-label={`Open ${person.name?.trim() || "unknown person"} group`}
      />

      <div className="pointer-events-none relative z-10 grid aspect-square w-full grid-cols-2 gap-2 overflow-hidden rounded-2xl">
        {[0, 1, 2, 3].map((index) => {
          const mediaId = person.sample_media_ids[index];
          const src =
            index === 0 && person.thumbnail_url
              ? resolveMediaUrl(person.thumbnail_url, null, mediaId, true)
              : resolveMediaUrl(null, null, mediaId, true);
          return (
            <div
              key={mediaId ? mediaId : `empty-${person.id}-${index}`}
              className="relative h-full w-full overflow-hidden rounded-xl"
            >
              {mediaId && src ? (
                <Image
                  src={src}
                  alt="Person photo"
                  fill
                  className="border border-[var(--frost)] object-cover"
                  sizes="(max-width: 768px) 25vw, 10vw"
                  unoptimized
                />
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="pointer-events-none relative z-10 mt-4 border-t border-[var(--frost-soft)] pt-3">
        <div className="flex min-h-8 min-w-0 items-center gap-2">
          {isEditing ? (
            <div className="pointer-events-auto flex w-full flex-1 items-center gap-1.5 overflow-hidden">
              <input
                type="text"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitName();
                  if (e.key === "Escape") {
                    setNameInput(person.name ?? "");
                    setIsEditing(false);
                  }
                }}
                placeholder="Enter a name..."
                className="min-w-0 flex-1 rounded-xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-3 py-1.5 text-sm text-[color:var(--near-white)] outline-none focus:border-[color:var(--blue)]"
              />
              <button
                type="button"
                onClick={submitName}
                disabled={nameMutation.isPending}
                className="icon-button shrink-0"
                aria-label="Save name"
              >
                {nameMutation.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Check className="h-3 w-3" />
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setNameInput(person.name ?? "");
                  setIsEditing(false);
                }}
                className="icon-button shrink-0"
                aria-label="Cancel"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ) : (
            <>
              <p className="flex-1 truncate text-base font-medium text-foreground">
                {person.name?.trim() ? (
                  person.name
                ) : (
                  <span className="text-muted-foreground font-normal">
                    Unknown person
                  </span>
                )}
              </p>
              <button
                type="button"
                onClick={() => {
                  setIsEditing(true);
                }}
                className="icon-button pointer-events-auto shrink-0"
                aria-label="Edit name"
              >
                <Pencil className="h-3 w-3" />
              </button>
            </>
          )}
        </div>

        <span className="mt-2 inline-flex rounded-full border border-[var(--frost)] px-2.5 py-1 text-xs font-medium text-[color:var(--silver)]">
          {person.face_count} {person.face_count === 1 ? "photo" : "photos"}
        </span>
      </div>
    </article>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function PeoplePage() {
  const queryClient = useQueryClient();
  const [selectedPersonId, setSelectedPersonId] = useState<number | null>(null);
  const [previewMedia, setPreviewMedia] = useState<PreviewMedia | null>(null);

  const {
    data: people,
    isLoading,
    error,
    isFetching,
  } = useQuery({
    queryKey: ["people"],
    queryFn: getPeople,
    refetchInterval: 15000,
  });

  const selectedPersonQuery = useQuery({
    queryKey: ["person-images", selectedPersonId],
    queryFn: () => getPersonImages(selectedPersonId as number),
    enabled: selectedPersonId !== null,
  });

  const clusterMutation = useMutation({
    mutationFn: triggerFaceClustering,
    onSuccess: () => {
      toast.success("Face clustering queued");
      queryClient.invalidateQueries({ queryKey: ["people"] });
    },
    onError: () => {
      toast.error("Face clustering failed");
    },
  });

  const wrongPersonMutation = useMutation({
    mutationFn: ({
      personId,
      faceIds,
    }: {
      personId: number;
      faceIds: number[];
    }) =>
      submitPersonFeedbackWrongPerson(
        personId,
        faceIds,
        "This photo is grouped under the wrong person.",
      ),
    onSuccess: () => {
      toast.success("Wrong-person feedback saved");
      queryClient.invalidateQueries({ queryKey: ["people"] });
      if (selectedPersonId !== null) {
        queryClient.invalidateQueries({
          queryKey: ["person-images", selectedPersonId],
        });
      }
    },
    onError: () => {
      toast.error("Could not save wrong-person feedback");
    },
  });

  return (
    <div className="page-shell bg-[hsl(var(--background))] text-[hsl(var(--foreground))]">
      <div className="container-shell py-10 md:py-14">
        {/* Page header */}
        <div className="page-enter mb-10 flex flex-col gap-6 border-b border-[var(--frost)] pb-8 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <h1 className="section-heading mb-4 text-5xl font-medium text-[color:var(--near-white)] md:text-6xl">
              People
            </h1>
            <p className="muted-copy text-sm leading-6 text-[color:var(--silver)]">
              Photos grouped by person, detected and clustered entirely on your
              device.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() =>
                queryClient.invalidateQueries({ queryKey: ["people"] })
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
              disabled={clusterMutation.isPending}
              className="white-pill px-5 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            >
              {clusterMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Re-cluster faces
            </button>
          </div>
        </div>

        {/* Loading state rendering layout */}
        {isLoading && (
          <div className="flex items-center justify-center py-32">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl px-8 py-14 text-center border border-destructive/50 bg-destructive/5">
            <p className="font-medium text-[color:var(--red)]">
              Failed to load people
            </p>
          </div>
        )}

        {/* Empty state container dashboard */}
        {people && people.length === 0 && (
          <div className="frost-panel mx-auto max-w-md rounded-3xl border border-[var(--frost)] px-8 py-14 text-center">
            <Users className="mx-auto mb-4 h-10 w-10 text-[color:var(--muted)]" />
            <p className="mb-2 font-medium text-[color:var(--near-white)]">
              No people found yet
            </p>
            <p className="mb-6 text-sm leading-6 text-[color:var(--silver)]">
              Upload photos with faces, then run face clustering.
            </p>
            <button
              type="button"
              onClick={() => clusterMutation.mutate()}
              disabled={clusterMutation.isPending}
              className="white-pill px-5 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              Run face clustering
            </button>
          </div>
        )}

        {/* People dashboard visualization matrix */}
        {people && people.length > 0 && (
          <div className="page-enter">
            <div className="mb-8 grid gap-3 sm:grid-cols-2">
              <div className="frost-panel rounded-2xl border border-[var(--frost)] p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-[color:var(--muted)]">
                  People found
                </p>
                <p className="mt-2 text-3xl font-light text-[color:var(--near-white)]">
                  {people.length}
                </p>
              </div>
              <div className="frost-panel rounded-2xl border border-[var(--frost)] p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-[color:var(--muted)]">
                  Total faces
                </p>
                <p className="mt-2 text-3xl font-light text-[color:var(--near-white)]">
                  {people.reduce((sum, p) => sum + p.face_count, 0)}
                </p>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {people.map((person) => (
                <PersonCard
                  key={person.id}
                  person={person}
                  onClick={() => setSelectedPersonId(person.id)}
                  onNameSaved={() =>
                    queryClient.invalidateQueries({ queryKey: ["people"] })
                  }
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Person detail sub-gallery display modal */}
      {selectedPersonId !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 backdrop-blur-md"
          role="dialog"
          aria-modal="true"
          aria-labelledby="person-modal-title"
        >
          <div className="frost-panel page-enter relative max-h-[90dvh] w-full max-w-6xl overflow-hidden rounded-3xl border border-[var(--frost)] bg-[hsl(var(--background))] shadow-2xl">
            <button
              type="button"
              onClick={() => setSelectedPersonId(null)}
              className="icon-button absolute right-4 top-4 z-20 border border-[var(--frost)] bg-[hsl(var(--background))]/80 text-[color:var(--near-white)] hover:bg-[color:var(--surface-hover)]"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>

            <div className="border-b border-[var(--frost)] bg-[color:var(--surface-soft)] px-6 py-5">
              <h2
                id="person-modal-title"
                className="text-xl font-medium text-[color:var(--near-white)]"
              >
                {selectedPersonQuery.data?.person_name?.trim() ||
                  "Unknown person"}
              </h2>
              {selectedPersonQuery.data && (
                <div className="mt-4 flex gap-3">
                  <FeedbackActions
                    personId={selectedPersonId}
                    personName={selectedPersonQuery.data?.person_name}
                    images={selectedPersonQuery.data?.images || []}
                    onFeedbackApplied={() => {
                      queryClient.invalidateQueries({
                        queryKey: ["person-images", selectedPersonId],
                      });
                    }}
                  />
                </div>
              )}
            </div>

            <div className="max-h-[calc(90dvh-76px)] overflow-y-auto bg-[hsl(var(--background))] p-6">
              {selectedPersonQuery.isLoading && (
                <div className="flex items-center justify-center py-24">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              )}

              {selectedPersonQuery.isError && (
                <div className="py-16 text-center text-destructive font-medium">
                  Failed to load photos.
                </div>
              )}

              {selectedPersonQuery.data && (
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
                  {selectedPersonQuery.data.images.map((img) => {
                    const faceIds = img.faces.map((face) => face.id);
                    const imageSrc = resolveMediaUrl(
                      img.thumbnail_url,
                      null,
                      img.media_id,
                      true,
                    );

                    return (
                      <article
                        key={img.media_id}
                        className="frost-panel card-hover group overflow-hidden rounded-3xl border border-[var(--frost)]"
                      >
                        <button
                          type="button"
                          onClick={() =>
                            setPreviewMedia({
                              id: img.media_id,
                              filename: img.filename,
                            })
                          }
                          className="block w-full text-left"
                          aria-label={`Preview ${img.filename}`}
                        >
                          <div className="relative aspect-square overflow-hidden bg-[color:var(--surface-soft)]">
                            {imageSrc ? (
                              <Image
                                src={imageSrc}
                                alt={img.filename}
                                fill
                                className="object-cover transition-transform duration-300 group-hover:scale-105"
                                sizes="(max-width: 768px) 50vw, 25vw"
                                unoptimized
                              />
                            ) : null}
                          </div>
                        </button>
                        <div className="space-y-3 border-t border-[var(--frost-soft)] bg-[color:var(--surface-soft)] p-3">
                          <p className="text-xs text-[color:var(--silver)]">
                            {img.faces.length}{" "}
                            {img.faces.length === 1 ? "face" : "faces"} detected
                          </p>
                          <button
                            type="button"
                            onClick={() => {
                              if (selectedPersonId === null) {
                                return;
                              }
                              wrongPersonMutation.mutate({
                                personId: selectedPersonId,
                                faceIds,
                              });
                            }}
                            disabled={
                              faceIds.length === 0 ||
                              wrongPersonMutation.isPending
                            }
                            className="frost-button w-full justify-center px-3 py-2 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {wrongPersonMutation.isPending
                              ? "Saving..."
                              : "Wrong person"}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Linked Image Preview Modal Context Integration */}
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
