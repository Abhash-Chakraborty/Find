"use client";

import { LockKeyhole, Map as MapIcon, ShieldCheck } from "lucide-react";
import Link from "next/link";

interface MapPrivacySettingsProps {
  enabled: boolean | undefined;
  pending: boolean;
  onChange: (enabled: boolean) => void;
}

export function MapPrivacySettings({
  enabled,
  pending,
  onChange,
}: MapPrivacySettingsProps) {
  const checked = enabled ?? false;

  return (
    <section
      id="private-map"
      aria-labelledby="private-map-heading"
      className="overflow-hidden rounded-2xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)] shadow-[0_18px_60px_rgba(0,0,0,0.08)]"
    >
      <div className="flex flex-col gap-5 p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
        <div className="flex min-w-0 gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[color:var(--surface-hover)] text-[color:var(--silver)]">
            <MapIcon aria-hidden="true" size={21} />
          </span>
          <div>
            <h2
              id="private-map-heading"
              className="text-base font-semibold text-[color:var(--near-white)]"
            >
              Private photo map
            </h2>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-[color:var(--silver)]">
              Off by default. When enabled, newly analyzed or reprocessed photos
              may store GPS coordinates found in their EXIF metadata. Existing
              photos are unchanged until you reprocess them.
            </p>
          </div>
        </div>

        <button
          type="button"
          role="switch"
          aria-label="Enable private photo map"
          aria-checked={checked}
          disabled={enabled === undefined || pending}
          onClick={() => onChange(!checked)}
          className="relative h-7 w-12 shrink-0 rounded-full border border-[color:var(--frost-strong)] bg-[color:var(--surface-hover)] transition disabled:cursor-wait disabled:opacity-50 aria-checked:border-[color:var(--near-white)] aria-checked:bg-[color:var(--near-white)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--void)]"
        >
          <span
            aria-hidden="true"
            className="absolute left-1 top-1 size-[1.125rem] rounded-full bg-white shadow transition-transform"
            style={{ transform: checked ? "translateX(1.25rem)" : undefined }}
          />
        </button>
      </div>

      <div className="grid gap-px border-t border-[color:var(--frost)] bg-[color:var(--frost)] sm:grid-cols-2">
        <div className="flex gap-3 bg-[color:var(--void)]/75 p-4">
          <ShieldCheck
            aria-hidden="true"
            className="mt-0.5 shrink-0 text-[color:var(--green)]"
            size={18}
          />
          <p className="text-xs leading-5 text-[color:var(--silver)]">
            The map uses bundled Natural Earth geometry. It never requests
            online map tiles or reverse geocoding.
          </p>
        </div>
        <div className="flex items-start justify-between gap-3 bg-[color:var(--void)]/75 p-4">
          <div className="flex gap-3">
            <LockKeyhole
              aria-hidden="true"
              className="mt-0.5 shrink-0 text-[color:var(--blue)]"
              size={18}
            />
            <p className="text-xs leading-5 text-[color:var(--silver)]">
              Hidden, vaulted, deleted, and other users&apos; photos stay off
              the map.
            </p>
          </div>
          {checked && (
            <Link
              href="/map"
              className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-[color:var(--near-white)] hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
            >
              Open map
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}
