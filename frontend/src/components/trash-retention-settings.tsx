"use client";

import { Clock3, Info } from "lucide-react";

interface TrashRetentionSettingsProps {
  value: number;
  pending: boolean;
  onChange: (days: number) => void;
}

const PRESETS = [7, 30, 90, 0] as const;

export function TrashRetentionSettings({
  value,
  pending,
  onChange,
}: TrashRetentionSettingsProps) {
  return (
    <section
      id="trash-retention"
      className="rounded-2xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)] p-5 sm:p-6"
      aria-labelledby="trash-retention-heading"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3">
          <Clock3 className="mt-0.5 h-5 w-5 text-[color:var(--silver)]" />
          <div>
            <div className="flex items-center gap-2">
              <h2 id="trash-retention-heading" className="font-semibold">
                Trash retention
              </h2>
              <button
                type="button"
                title="Expired items are permanently removed when Trash is opened. Set Never to require manual emptying."
                aria-label="Expired items are permanently removed when Trash is opened. Set Never to require manual emptying."
                className="rounded text-[color:var(--muted)] outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
              >
                <Info className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <p className="mt-1 text-sm text-[color:var(--silver)]">
              Permanently delete trashed photos after a chosen delay.
            </p>
          </div>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {PRESETS.map((days) => (
          <button
            key={days}
            type="button"
            disabled={pending}
            aria-pressed={value === days}
            onClick={() => onChange(days)}
            className={`rounded-xl border px-4 py-2 text-sm transition ${
              value === days
                ? "border-[color:var(--near-white)] bg-[color:var(--near-white)] text-[color:var(--void)]"
                : "border-[color:var(--frost)] text-[color:var(--silver)] hover:bg-[color:var(--surface-hover)]"
            }`}
          >
            {days === 0 ? "Never" : `${days} days`}
          </button>
        ))}
        <label className="flex items-center gap-2 rounded-xl border border-[color:var(--frost)] px-3 py-1.5 text-sm text-[color:var(--silver)]">
          Custom
          <input
            type="number"
            min={1}
            max={3650}
            value={
              PRESETS.includes(value as (typeof PRESETS)[number]) ? "" : value
            }
            placeholder="days"
            disabled={pending}
            onChange={(event) => {
              const days = Number(event.target.value);
              if (Number.isInteger(days) && days >= 1 && days <= 3650) {
                onChange(days);
              }
            }}
            className="w-20 bg-transparent text-right text-[color:var(--near-white)] outline-none"
          />
        </label>
      </div>
    </section>
  );
}
