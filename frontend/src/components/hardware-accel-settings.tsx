"use client";

import { useQuery } from "@tanstack/react-query";
import { Cpu, Gauge, MonitorCog } from "lucide-react";
import { type AccelMode, getHardwareReport, getRuntimeConfig } from "@/lib/api";

const MODES: { value: AccelMode; label: string; hint: string }[] = [
  {
    value: "auto",
    label: "Auto",
    hint: "Use the best available accelerator, otherwise CPU.",
  },
  {
    value: "gpu",
    label: "GPU",
    hint: "Prefer GPU and fall back safely when it is unavailable.",
  },
  { value: "cpu", label: "CPU", hint: "Force CPU on any supported machine." },
];

interface HardwareAccelSettingsProps {
  value?: AccelMode;
  onChange?: (mode: AccelMode) => void;
  pending?: boolean;
}

export function HardwareAccelSettings({
  value,
  onChange,
  pending = false,
}: HardwareAccelSettingsProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["hardware-report"],
    queryFn: getHardwareReport,
  });
  const { data: runtime } = useQuery({
    queryKey: ["runtime-config"],
    queryFn: getRuntimeConfig,
  });
  const selected: AccelMode = value ?? data?.accel_mode ?? "auto";

  return (
    <section
      id="hardware"
      data-testid="accel-settings"
      aria-labelledby="accel-heading"
      className="overflow-hidden rounded-2xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)] shadow-[0_18px_60px_rgba(0,0,0,0.08)]"
    >
      <div className="flex gap-4 p-5 sm:p-6">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[color:var(--green-soft)] text-[color:var(--green)]">
          <Gauge aria-hidden="true" size={21} />
        </span>
        <div>
          <h2
            id="accel-heading"
            className="text-base font-semibold tracking-tight"
          >
            Hardware acceleration
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[color:var(--silver)]">
            Choose how the installed AI artifact schedules inference. Auto is
            the safest default and falls back without interrupting uploads.
          </p>
        </div>
      </div>

      <fieldset className="grid gap-px border-y border-[color:var(--frost)] bg-[color:var(--frost)] sm:grid-cols-3">
        <legend className="sr-only">Acceleration mode</legend>
        {MODES.map((mode, index) => {
          const gpuNotInstalled =
            mode.value === "gpu" &&
            runtime !== undefined &&
            runtime.build_profile !== "nvidia" &&
            runtime.build_profile !== "development";

          return (
            <label
              key={mode.value}
              data-testid={`accel-option-${mode.value}`}
              className="group relative flex min-h-28 cursor-pointer flex-col gap-2 bg-[color:var(--void)]/90 p-4 transition hover:bg-[color:var(--surface-hover)] has-[:checked]:bg-[color:var(--blue-soft)] has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50"
              title={
                gpuNotInstalled
                  ? "GPU runtime is not included in this installed build."
                  : undefined
              }
            >
              <input
                type="radio"
                name="accel-mode"
                value={mode.value}
                checked={selected === mode.value}
                disabled={pending || gpuNotInstalled}
                onChange={() => onChange?.(mode.value)}
                className="peer sr-only"
              />
              <span className="flex items-center justify-between gap-3 text-sm font-semibold">
                <span className="flex items-center gap-2">
                  {index === 0 ? (
                    <MonitorCog aria-hidden="true" size={16} />
                  ) : (
                    <Cpu aria-hidden="true" size={16} />
                  )}
                  {mode.label}
                </span>
                <span className="size-4 rounded-full border border-[color:var(--frost-strong)] bg-[color:var(--void)] shadow-[inset_0_0_0_3px_var(--void)] peer-checked:border-[color:var(--blue)] peer-checked:bg-[color:var(--blue)]" />
              </span>
              <span className="text-xs leading-5 text-[color:var(--silver)]">
                {gpuNotInstalled
                  ? "Not installed in this modular build."
                  : mode.hint}
              </span>
            </label>
          );
        })}
      </fieldset>

      {isLoading && (
        <p
          className="px-5 py-4 text-sm text-[color:var(--silver)]"
          data-testid="accel-loading"
        >
          Detecting hardware…
        </p>
      )}
      {isError && (
        <p
          className="px-5 py-4 text-sm text-[color:var(--red)]"
          data-testid="accel-error"
          role="alert"
        >
          Couldn&apos;t detect hardware capabilities.
        </p>
      )}

      {data && (
        <div
          className="grid gap-3 p-5 text-sm sm:grid-cols-2 sm:p-6"
          data-testid="accel-status"
        >
          <p className="rounded-xl border border-[color:var(--frost)] bg-[color:var(--void)]/65 p-3 text-[color:var(--silver)]">
            <span className="block text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[color:var(--muted)]">
              Detected
            </span>
            <strong
              className="mt-1 block text-[color:var(--near-white)]"
              data-testid="accel-detected"
            >
              {data.capabilities.has_gpu
                ? `GPU available (${data.capabilities.best_gpu_provider})`
                : "No GPU detected — CPU only"}
            </strong>
          </p>
          <p className="rounded-xl border border-[color:var(--frost)] bg-[color:var(--void)]/65 p-3 text-[color:var(--silver)]">
            <span className="block text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[color:var(--muted)]">
              Currently using
            </span>
            <strong
              className="mt-1 block text-[color:var(--near-white)]"
              data-testid="accel-using"
            >
              {data.resolved.using_gpu ? "GPU" : "CPU"}
            </strong>
          </p>
          {data.resolved.notice && (
            <p
              className="rounded-xl bg-[color:var(--orange-soft)] p-3 text-xs leading-5 text-[color:var(--silver)] sm:col-span-2"
              data-testid="accel-notice"
              role="status"
            >
              {data.resolved.notice}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
