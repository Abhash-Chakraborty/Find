"use client";

import { useMutation } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

type FeedbackRatingProps = {
  label: string;
  onRate: (rating: number) => Promise<unknown>;
};

export function FeedbackRating({ label, onRate }: FeedbackRatingProps) {
  const [selectedRating, setSelectedRating] = useState<number | null>(null);

  const ratingMutation = useMutation({
    mutationFn: onRate,
    onSuccess: (_, rating) => {
      setSelectedRating(rating);
      toast.success("Feedback saved");
    },
    onError: () => {
      toast.error("Failed to save feedback");
    },
  });

  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-3 py-2">
      {label ? (
        <span className="text-xs font-medium leading-4 text-[color:var(--silver)]">
          {label}
        </span>
      ) : null}
      <fieldset className="flex flex-wrap items-center gap-1">
        <legend className="sr-only">{label} rating</legend>
        {[1, 2, 3, 4, 5].map((rating) => {
          const isActive = selectedRating !== null && rating <= selectedRating;
          return (
            <button
              key={rating}
              type="button"
              onClick={() => ratingMutation.mutate(rating)}
              disabled={ratingMutation.isPending}
              className={`rounded-full p-1 transition ${
                isActive
                  ? "text-[color:var(--blue)]"
                  : "text-[color:var(--muted)] hover:text-[color:var(--near-white)]"
              } disabled:cursor-not-allowed disabled:opacity-60`}
              aria-label={`Rate ${label} ${rating} out of 5`}
            >
              <Star
                className={`h-3.5 w-3.5 ${isActive ? "fill-current" : ""}`}
              />
            </button>
          );
        })}
      </fieldset>
    </div>
  );
}
