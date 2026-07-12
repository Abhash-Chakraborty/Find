"use client";

import { useQuery } from "@tanstack/react-query";
import { Boxes, Cpu, Power, ServerCog } from "lucide-react";
import type { ReactNode } from "react";
import { getRuntimeConfig } from "@/lib/api";

interface AiRuntimeSettingsProps {
  enabled: boolean | undefined;
  pending: boolean;
  onChange: (enabled: boolean) => void;
  mode: "disabled" | "full" | "mock" | "remote" | undefined;
  supportedModes: string[];
  onModeChange: (mode: "disabled" | "full" | "mock") => void;
}

const PROFILE_COMMANDS = [
  ["No AI", "docker compose -f compose.no-ai.yml up --build"],
  ["Mock", "docker compose -f compose.mock.yml up --build"],
  ["CPU AI", "docker compose -f compose.cpu.yml up --build"],
  ["NVIDIA AI", "docker compose up --build"],
] as const;

export function AiRuntimeSettings({
  enabled,
  pending,
  onChange,
  mode,
  supportedModes,
  onModeChange,
}: AiRuntimeSettingsProps) {
  const runtime = useQuery({
    queryKey: ["runtime-config"],
    queryFn: getRuntimeConfig,
    retry: false,
    refetchInterval: 30_000,
  });
  const checked = enabled ?? runtime.data?.ai_enabled ?? false;

  return (
    <section
      aria-labelledby="ai-runtime-heading"
      className="overflow-hidden rounded-2xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)] shadow-[0_18px_60px_rgba(0,0,0,0.08)]"
    >
      <div className="flex flex-col gap-5 p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
        <div className="flex min-w-0 gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[color:var(--blue-soft)] text-[color:var(--blue)]">
            <Cpu aria-hidden="true" size={21} />
          </span>
          <div>
            <h2 id="ai-runtime-heading" className="text-base font-semibold">
              Local AI runtime
            </h2>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-[color:var(--silver)]">
              Control new analysis jobs from here. The installed build stays
              modular: this switch cannot download CUDA or add model packages.
            </p>
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-label="Enable local AI processing"
          aria-checked={checked}
          disabled={enabled === undefined || pending}
          onClick={() => onChange(!checked)}
          className="relative h-7 w-12 shrink-0 rounded-full border border-[color:var(--frost-strong)] bg-[color:var(--surface-hover)] transition disabled:cursor-wait disabled:opacity-50 aria-checked:border-[color:var(--green)] aria-checked:bg-[color:var(--green)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
        >
          <span
            aria-hidden="true"
            className="absolute left-1 top-1 size-[1.125rem] rounded-full bg-white shadow transition-transform"
            style={{ transform: checked ? "translateX(1.25rem)" : undefined }}
          />
        </button>
      </div>

      <div className="grid gap-px border-t border-[color:var(--frost)] bg-[color:var(--frost)] md:grid-cols-3">
        <RuntimeDatum
          icon={<Boxes aria-hidden="true" size={17} />}
          label="Installed artifact"
          value={
            runtime.data?.build_profile ??
            (runtime.isPending ? "Detecting…" : "Unavailable")
          }
        />
        <RuntimeDatum
          icon={<Power aria-hidden="true" size={17} />}
          label="Applied mode"
          value={runtime.data?.applied_mode ?? "Unknown"}
        />
        <RuntimeDatum
          icon={<ServerCog aria-hidden="true" size={17} />}
          label="Worker"
          value={runtime.data?.worker.health.state ?? "Unknown"}
        />
      </div>

      {(runtime.data?.unavailable_reason || runtime.data?.restart_required) && (
        <p
          role="status"
          className="border-t border-[color:var(--frost)] bg-[color:var(--orange-soft)] px-5 py-3 text-sm text-[color:var(--silver)]"
        >
          {runtime.data.unavailable_reason ??
            "Start a compatible artifact to apply this runtime."}
        </p>
      )}

      <div className="border-t border-[color:var(--frost)] px-5 py-4">
        <label
          htmlFor="ai-runtime-mode"
          className="block text-sm font-semibold text-[color:var(--near-white)]"
        >
          Processing mode
        </label>
        <p className="mt-1 text-xs leading-5 text-[color:var(--silver)]">
          Switch instantly between the modes already installed in this build.
        </p>
        <select
          id="ai-runtime-mode"
          value={mode ?? "disabled"}
          disabled={mode === undefined || pending}
          onChange={(event) =>
            onModeChange(event.target.value as "disabled" | "full" | "mock")
          }
          className="mt-3 h-11 w-full rounded-xl border border-[color:var(--frost)] bg-[color:var(--void)] px-3 text-sm text-[color:var(--near-white)] outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)] sm:max-w-xs"
        >
          {mode && !supportedModes.includes(mode) && (
            <option value={mode} disabled>
              {mode} (not installed)
            </option>
          )}
          {supportedModes.map((supportedMode) => (
            <option key={supportedMode} value={supportedMode}>
              {supportedMode === "full"
                ? "Full local AI"
                : supportedMode === "mock"
                  ? "Mock AI"
                  : "AI disabled"}
            </option>
          ))}
        </select>
      </div>

      <details className="border-t border-[color:var(--frost)] px-5 py-4">
        <summary className="cursor-pointer text-sm font-semibold">
          Change the installed build
        </summary>
        <p className="mt-2 text-xs leading-5 text-[color:var(--silver)]">
          Choose one command on the host. Only that artifact&apos;s dependencies
          are installed; switching from the dashboard alone would be misleading.
        </p>
        <div className="mt-3 grid gap-2">
          {PROFILE_COMMANDS.map(([label, command]) => (
            <div
              key={label}
              className="grid gap-1 rounded-xl bg-[color:var(--void)] p-3 sm:grid-cols-[7rem_1fr] sm:items-center"
            >
              <strong className="text-xs">{label}</strong>
              <code className="overflow-x-auto text-xs text-[color:var(--silver)]">
                {command}
              </code>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

function RuntimeDatum({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-3 bg-[color:var(--void)]/75 p-4">
      <span className="text-[color:var(--blue)]">{icon}</span>
      <span>
        <span className="block text-[0.68rem] uppercase tracking-wider text-[color:var(--muted)]">
          {label}
        </span>
        <strong className="mt-0.5 block text-sm capitalize">{value}</strong>
      </span>
    </div>
  );
}
