import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  getPeople,
  type PersonImagesResponse,
  submitPersonFeedbackCorrect,
  submitPersonFeedbackMerge,
  submitPersonFeedbackSplit,
  submitPersonFeedbackWrongPerson,
} from "@/lib/api";

interface FeedbackActionsProps {
  personId: number;
  personName?: string | null;
  images: PersonImagesResponse["images"];
  onFeedbackApplied: () => void;
}

// Face selector for split/wrong-person actions
interface FaceSelectorModalProps {
  title: string;
  description: string;
  images: PersonImagesResponse["images"];
  onSubmit: (faceIds: number[], reason?: string) => Promise<void>;
  onCancel: () => void;
  isLoading: boolean;
  reason?: string;
}

function FaceSelectorModal({
  title,
  description,
  images,
  onSubmit,
  onCancel,
  isLoading,
  reason,
}: FaceSelectorModalProps) {
  const [selectedFaceIds, setSelectedFaceIds] = useState<number[]>([]);
  const [localReason, setLocalReason] = useState(reason || "");

  const toggleFace = (faceId: number) => {
    setSelectedFaceIds((prev) => {
      if (prev.includes(faceId)) {
        return prev.filter((id) => id !== faceId);
      }
      return [...prev, faceId];
    });
  };

  const toggleAllInImage = (faceIds: number[]) => {
    setSelectedFaceIds((prev) => {
      const selectedInImage = faceIds.filter((id) => prev.includes(id));
      if (selectedInImage.length === faceIds.length) {
        return prev.filter((id) => !faceIds.includes(id));
      }
      return Array.from(new Set([...prev, ...faceIds]));
    });
  };

  const allFaceIds = selectedFaceIds;

  const handleSubmit = async () => {
    if (allFaceIds.length === 0) {
      toast.error("Please select at least one face");
      return;
    }
    try {
      await onSubmit(allFaceIds, localReason.trim() || undefined);
    } catch {
      // Error handled by caller
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 px-4 backdrop-blur-md">
      <div className="frost-panel max-h-[86dvh] w-full max-w-5xl overflow-hidden rounded-3xl border border-[var(--frost)] bg-[hsl(var(--background))]">
        {/* Header */}
        <div className="border-b border-[var(--frost)] bg-[color:var(--surface-soft)] px-6 py-5">
          <h3 className="text-lg font-medium text-[color:var(--near-white)]">
            {title}
          </h3>
          <p className="mt-1 text-sm text-[color:var(--silver)]">
            {description}
          </p>
        </div>

        {/* Content */}
        <div className="max-h-[calc(86dvh-190px)] overflow-y-auto bg-[hsl(var(--background))] p-6">
          {/* Face Grid */}
          <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {images.map((img) => (
              <div
                key={img.media_id}
                className="frost-panel rounded-2xl border border-[var(--frost)] p-3"
              >
                <p className="mb-2 text-xs font-semibold text-[color:var(--silver)]">
                  {img.filename}
                </p>
                <div className="flex flex-col gap-2">
                  {img.faces.map((face, faceIndex) => (
                    <button
                      key={face.id}
                      type="button"
                      onClick={() => toggleFace(face.id)}
                      className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                        selectedFaceIds.includes(face.id)
                          ? "border-[color:var(--blue)] bg-[color:var(--blue-soft)] text-[color:var(--blue)]"
                          : "border-[var(--frost)] text-[color:var(--silver)] hover:border-[var(--frost-strong)]"
                      }`}
                    >
                      Face {faceIndex + 1}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      toggleAllInImage(img.faces.map((face) => face.id))
                    }
                    className="rounded-lg border border-[var(--frost-soft)] bg-[color:var(--surface-soft)] px-2 py-1 text-xs text-[color:var(--muted)] hover:bg-[color:var(--surface-hover)]"
                  >
                    {img.faces.every((face) =>
                      selectedFaceIds.includes(face.id),
                    )
                      ? "Deselect all"
                      : "Select all"}
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Reason Input */}
          <div className="mb-6">
            <label
              htmlFor="feedback-reason"
              className="mb-2 block text-xs font-semibold uppercase tracking-wider text-[color:var(--muted)]"
            >
              Optional reason
            </label>
            <textarea
              id="feedback-reason"
              value={localReason}
              onChange={(e) => setLocalReason(e.target.value)}
              placeholder="Why are you making this change?"
              className="w-full rounded-xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-3 py-2 text-sm text-[color:var(--near-white)] placeholder-[color:var(--muted)] outline-none focus:border-blue-500"
              rows={3}
            />
          </div>

          {/* Count */}
          <div className="mb-6 text-sm text-[color:var(--silver)]">
            Selected: <span className="font-semibold">{allFaceIds.length}</span>{" "}
            face{allFaceIds.length !== 1 ? "s" : ""}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 border-t border-[var(--frost)] bg-[color:var(--surface-soft)] px-6 py-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={isLoading}
            className="frost-button px-4 py-2 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isLoading || allFaceIds.length === 0}
            className="white-pill min-w-24 justify-center px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "Confirm"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// Merge selector - choose which person to merge with
interface MergeSelectorProps {
  currentPersonId: number;
  onSelect: (targetPersonId: number) => void;
  onCancel: () => void;
}

function MergeSelector({
  currentPersonId,
  onSelect,
  onCancel,
}: MergeSelectorProps) {
  const { data: people, isError } = useQuery({
    queryKey: ["people"],
    queryFn: getPeople,
  });

  const otherPeople = people?.filter((p) => p.id !== currentPersonId) || [];

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 px-4 backdrop-blur-md">
      <div className="frost-panel max-h-[80dvh] w-full max-w-xl overflow-hidden rounded-3xl border border-[var(--frost)] bg-[hsl(var(--background))]">
        <div className="border-b border-[var(--frost)] bg-[color:var(--surface-soft)] px-6 py-5">
          <h3 className="text-lg font-medium text-[color:var(--near-white)]">
            Merge with person
          </h3>
          <p className="mt-1 text-sm text-[color:var(--silver)]">
            Select the person to merge with
          </p>
        </div>

        <div className="max-h-[calc(80dvh-140px)] overflow-y-auto bg-[hsl(var(--background))] p-6">
          {isError ? (
            <div className="text-center py-12">
              <p className="text-[color:var(--red)]">
                Failed to load people. Please try again.
              </p>
            </div>
          ) : otherPeople.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-[color:var(--silver)]">
                No other people found to merge with
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {otherPeople.map((person) => (
                <button
                  key={person.id}
                  type="button"
                  onClick={() => onSelect(person.id)}
                  className="frost-panel w-full rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-4 py-3 text-left transition hover:border-[var(--frost-strong)] hover:bg-[color:var(--surface-hover)]"
                >
                  <p className="font-medium text-[color:var(--near-white)]">
                    {person.name || "Unknown person"}
                  </p>
                  <p className="text-xs text-[color:var(--silver)]">
                    {person.face_count} photos
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-[var(--frost)] bg-[color:var(--surface-soft)] px-6 py-4">
          <button
            type="button"
            onClick={onCancel}
            className="w-full frost-button px-4 py-2 text-sm"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export function FeedbackActions({
  personId,
  images,
  onFeedbackApplied,
}: FeedbackActionsProps) {
  const queryClient = useQueryClient();
  const [showSplitModal, setShowSplitModal] = useState(false);
  const [showWrongPersonModal, setShowWrongPersonModal] = useState(false);
  const [showMergeSelector, setShowMergeSelector] = useState(false);
  const [showActionsMenu, setShowActionsMenu] = useState(false);

  const splitMutation = useMutation({
    mutationFn: ({ faceIds, reason }: { faceIds: number[]; reason?: string }) =>
      submitPersonFeedbackSplit(personId, faceIds, reason),
    onSuccess: () => {
      toast.success("Person group split successfully");
      setShowSplitModal(false);
      queryClient.invalidateQueries({ queryKey: ["people"] });
      onFeedbackApplied();
    },
    onError: (error) => {
      toast.error("Failed to split person group");
      console.error(error);
    },
  });

  const wrongPersonMutation = useMutation({
    mutationFn: ({ faceIds, reason }: { faceIds: number[]; reason?: string }) =>
      submitPersonFeedbackWrongPerson(personId, faceIds, reason),
    onSuccess: () => {
      toast.success("Face marked as wrong person");
      setShowWrongPersonModal(false);
      queryClient.invalidateQueries({ queryKey: ["people"] });
      onFeedbackApplied();
    },
    onError: (error) => {
      toast.error("Failed to mark face");
      console.error(error);
    },
  });

  const mergeMutation = useMutation({
    mutationFn: (targetPersonId: number) =>
      submitPersonFeedbackMerge(personId, targetPersonId),
    onSuccess: () => {
      toast.success("Person groups merged successfully");
      setShowMergeSelector(false);
      queryClient.invalidateQueries({ queryKey: ["people"] });
      onFeedbackApplied();
    },
    onError: (error) => {
      toast.error("Failed to merge person groups");
      console.error(error);
    },
  });

  const correctMutation = useMutation({
    mutationFn: () => submitPersonFeedbackCorrect(personId),
    onSuccess: () => {
      toast.success("Marked as correct grouping");
      setShowActionsMenu(false);
    },
    onError: (error) => {
      toast.error("Failed to save feedback");
      console.error(error);
    },
  });

  const handleMergeSelect = (targetPersonId: number) => {
    setShowMergeSelector(false);
    mergeMutation.mutate(targetPersonId);
  };

  return (
    <>
      {/* Actions Button */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setShowActionsMenu(!showActionsMenu)}
          className="frost-button inline-flex items-center gap-2 px-4 py-2 text-sm"
        >
          Actions
          <ChevronDown
            className={`h-3 w-3 transition ${
              showActionsMenu ? "rotate-180" : ""
            }`}
          />
        </button>

        {/* Dropdown Menu */}
        {showActionsMenu && (
          <div className="absolute left-0 top-full z-50 mt-2 w-56 overflow-hidden rounded-2xl border border-[var(--frost)] bg-[hsl(var(--background))] shadow-2xl">
            <button
              type="button"
              onClick={() => {
                setShowSplitModal(true);
                setShowActionsMenu(false);
              }}
              className="flex w-full items-center border-b border-[var(--frost-soft)] px-4 py-3 text-left text-sm font-medium text-[color:var(--near-white)] hover:bg-[color:var(--surface-hover)]"
            >
              Split group
            </button>
            <button
              type="button"
              onClick={() => {
                setShowMergeSelector(true);
                setShowActionsMenu(false);
              }}
              className="flex w-full items-center border-b border-[var(--frost-soft)] px-4 py-3 text-left text-sm font-medium text-[color:var(--near-white)] hover:bg-[color:var(--surface-hover)]"
            >
              Merge with another
            </button>
            <button
              type="button"
              onClick={() => {
                setShowWrongPersonModal(true);
                setShowActionsMenu(false);
              }}
              className="flex w-full items-center border-b border-[var(--frost-soft)] px-4 py-3 text-left text-sm font-medium text-[color:var(--near-white)] hover:bg-[color:var(--surface-hover)]"
            >
              Mark as wrong person
            </button>
            <button
              type="button"
              onClick={() => {
                correctMutation.mutate();
                setShowActionsMenu(false);
              }}
              disabled={correctMutation.isPending}
              className="flex w-full items-center px-4 py-3 text-left text-sm font-medium text-[color:var(--green)] hover:bg-[color:var(--surface-hover)] disabled:opacity-50"
            >
              {correctMutation.isPending ? "Saving..." : "Mark as correct"}
            </button>
          </div>
        )}
      </div>

      {/* Split Modal */}
      {showSplitModal && (
        <FaceSelectorModal
          title="Split person group"
          description="Select the faces that should be a separate person"
          images={images}
          onSubmit={async (faceIds, reason) => {
            await splitMutation.mutateAsync({ faceIds, reason });
          }}
          onCancel={() => setShowSplitModal(false)}
          isLoading={splitMutation.isPending}
        />
      )}

      {/* Wrong Person Modal */}
      {showWrongPersonModal && (
        <FaceSelectorModal
          title="Mark as wrong person"
          description="Select the faces that don't belong to this person"
          images={images}
          onSubmit={async (faceIds, reason) => {
            await wrongPersonMutation.mutateAsync({ faceIds, reason });
          }}
          onCancel={() => setShowWrongPersonModal(false)}
          isLoading={wrongPersonMutation.isPending}
        />
      )}

      {/* Merge Selector */}
      {showMergeSelector && (
        <MergeSelector
          currentPersonId={personId}
          onSelect={handleMergeSelect}
          onCancel={() => setShowMergeSelector(false)}
        />
      )}
    </>
  );
}
