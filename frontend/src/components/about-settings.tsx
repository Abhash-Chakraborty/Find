"use client";

import { useQuery } from "@tanstack/react-query";
import { BadgeInfo, Check, ClipboardCopy, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { getAppConfig, getRuntimeConfig } from "@/lib/api";
import { buildSupportSummary, formatWorkerAge } from "@/lib/support-summary";

type CopyState = "idle" | "copying" | "copied" | "error";

const WORKER_LABEL: Record<string, string> = {
  healthy: "Healthy",
  stale: "Stale",
  unknown: "Unknown",
  unavailable: "Unavailable",
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <dt className="text-sm text-[color:var(--silver)]">{label}</dt>
      {/* Wrap on phones, where the row is stacked and the value has a whole
          line to itself; only truncate from sm: up, where label and value
          share one line. `truncate` implies white-space: nowrap, so applying
          it unconditionally also gave this cell a max-content minimum. */}
      <dd className="break-words text-sm font-medium text-[color:var(--near-white)] sm:max-w-[60%] sm:truncate sm:text-right">
        {value}
      </dd>
    </div>
  );
}

export function AboutSettings() {
  const [copyState, setCopyState] = useState<CopyState>("idle");

  const config = useQuery({
    queryKey: ["app-config"],
    queryFn: getAppConfig,
    retry: false,
  });
  const runtime = useQuery({
    queryKey: ["runtime-config"],
    queryFn: getRuntimeConfig,
    retry: false,
  });

  const workerState = runtime.data?.worker.health.state ?? "unknown";
  const workerAgeSeconds = runtime.data?.worker.health.age_seconds ?? null;

  const summaryInput = {
    appVersion: config.data?.app_version ?? "unknown",
    buildProfile: config.data?.build_profile ?? "unknown",
    configuredMode: config.data?.configured_ml_mode ?? "unknown",
    appliedMode: config.data?.ml_mode ?? "unknown",
    aiEnabled: config.data?.ai_enabled ?? false,
    accelMode: config.data?.accel_mode ?? "unknown",
    workerState,
    workerAgeSeconds,
    restartRequired: runtime.data?.restart_required ?? false,
  };

  const onCopy = async () => {
    setCopyState("copying");
    try {
      await navigator.clipboard.writeText(buildSupportSummary(summaryInput));
      setCopyState("copied");
    } catch {
      // Clipboard access is denied in some browsers and insecure contexts.
      setCopyState("error");
    }
  };

  return (
    <section
      id="about"
      className="rounded-2xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)] p-5 sm:p-6"
      aria-labelledby="about-heading"
    >
      <div className="flex gap-3">
        <BadgeInfo
          aria-hidden="true"
          className="mt-0.5 h-5 w-5 shrink-0 text-[color:var(--silver)]"
        />
        <div className="min-w-0 flex-1">
          <h2
            id="about-heading"
            className="text-base font-semibold tracking-tight"
          >
            About this instance
          </h2>
          <p className="mt-1 text-sm text-[color:var(--silver)]">
            Version and runtime state, plus a short summary you can paste into a
            bug report. The summary carries no paths, filenames, credentials, or
            identifiers.
          </p>

          {config.isError ? (
            <p
              role="alert"
              data-testid="about-error"
              className="mt-4 rounded-xl border border-[color:var(--red)]/30 bg-[color:var(--red-soft)] px-4 py-3 text-sm"
            >
              Couldn&apos;t read the instance version. Check the local API.
            </p>
          ) : (
            <dl
              data-testid="about-details"
              className="mt-4 divide-y divide-[color:var(--frost-soft)]"
            >
              <Row
                label="App version"
                value={
                  config.isPending
                    ? "Loading…"
                    : (config.data?.app_version ?? "unknown")
                }
              />
              <Row
                label="Build profile"
                value={config.data?.build_profile ?? "unknown"}
              />
              <Row
                label="AI mode applied"
                value={
                  config.data
                    ? `${config.data.ml_mode}${
                        config.data.ai_enabled ? "" : " (AI off)"
                      }`
                    : "unknown"
                }
              />
              <Row
                label="Worker"
                value={`${WORKER_LABEL[workerState] ?? workerState} · last seen ${formatWorkerAge(
                  workerAgeSeconds,
                )}`}
              />
            </dl>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              data-testid="copy-support-summary"
              onClick={onCopy}
              aria-label="Copy support summary to the clipboard"
              aria-busy={copyState === "copying"}
              disabled={copyState === "copying"}
              className="inline-flex h-11 items-center gap-2 rounded-xl border border-[color:var(--frost)] px-4 text-sm font-medium text-[color:var(--silver)] outline-none transition hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--near-white)] active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[color:var(--blue)] disabled:cursor-wait disabled:opacity-60"
            >
              {copyState === "copying" ? (
                <LoaderCircle
                  aria-hidden="true"
                  className="animate-spin"
                  size={15}
                />
              ) : copyState === "copied" ? (
                <Check aria-hidden="true" size={15} />
              ) : (
                <ClipboardCopy aria-hidden="true" size={15} />
              )}
              Copy support summary
            </button>

            {/* Kept mounted so the status is announced rather than newly inserted. */}
            <p
              aria-live="polite"
              data-testid="copy-status"
              className={`min-h-5 text-sm ${
                copyState === "error"
                  ? "text-[color:var(--status-failed-text)]"
                  : "text-[color:var(--silver)]"
              }`}
            >
              {copyState === "copying" && "Copying support summary…"}
              {copyState === "copied" && "Support summary copied."}
              {copyState === "error" &&
                "Couldn't copy. Select the details above and copy manually."}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
