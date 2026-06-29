"use client";

/**
 * Hardware acceleration settings section.
 *
 * Renders the Auto/GPU/CPU toggle and reflects the backend's resolved plan
 * from `GET /api/config/hardware` — including the non-blocking CPU-fallback
 * notice when a GPU was requested but isn't available. This is the UI surface
 * of the Phase 5 speed/low-end goal.
 */

import { useQuery } from "@tanstack/react-query";
import { type AccelMode, getHardwareReport } from "@/lib/api";

const MODES: { value: AccelMode; label: string; hint: string }[] = [
  {
    value: "auto",
    label: "Auto",
    hint: "Use the best available accelerator, otherwise CPU.",
  },
  {
    value: "gpu",
    label: "GPU",
    hint: "Prefer GPU; automatically fall back to CPU if unavailable.",
  },
  { value: "cpu", label: "CPU", hint: "Force CPU. Works on any machine." },
];

interface HardwareAccelSettingsProps {
  /** Current selected mode (controlled). */
  value?: AccelMode;
  onChange?: (mode: AccelMode) => void;
}

export function HardwareAccelSettings({
  value,
  onChange,
}: HardwareAccelSettingsProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["hardware-report"],
    queryFn: getHardwareReport,
  });

  const selected: AccelMode = value ?? data?.accel_mode ?? "auto";

  return (
    <section data-testid="accel-settings" aria-labelledby="accel-heading">
      <h3 id="accel-heading">Hardware acceleration</h3>

      <fieldset>
        <legend className="sr-only">Acceleration mode</legend>
        {MODES.map((mode) => (
          <label key={mode.value} data-testid={`accel-option-${mode.value}`}>
            <input
              type="radio"
              name="accel-mode"
              value={mode.value}
              checked={selected === mode.value}
              onChange={() => onChange?.(mode.value)}
            />
            <span>{mode.label}</span>
            <span className="hint">{mode.hint}</span>
          </label>
        ))}
      </fieldset>

      {isLoading && <p data-testid="accel-loading">Detecting hardware…</p>}
      {isError && (
        <p data-testid="accel-error" role="alert">
          Couldn't detect hardware capabilities.
        </p>
      )}

      {data && (
        <div data-testid="accel-status">
          <p>
            Detected:{" "}
            <strong data-testid="accel-detected">
              {data.capabilities.has_gpu
                ? `GPU available (${data.capabilities.best_gpu_provider})`
                : "No GPU detected — CPU only"}
            </strong>
          </p>
          <p>
            Currently using:{" "}
            <strong data-testid="accel-using">
              {data.resolved.using_gpu ? "GPU" : "CPU"}
            </strong>
          </p>
          {data.resolved.notice && (
            <p data-testid="accel-notice" role="status">
              {data.resolved.notice}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
