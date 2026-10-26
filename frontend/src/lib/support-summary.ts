/**
 * Support summary formatting (pure, no React).
 *
 * Builds the short block behind Settings > About > "Copy support summary".
 *
 * The input type is a deliberately narrow allow-list: only the non-identifying
 * runtime facts below are accepted, so environment values, filesystem paths,
 * media metadata, filenames, credentials, session tokens, usernames, and
 * instance identifiers cannot reach the clipboard even by accident. Widening
 * this interface is the one change that needs a privacy review.
 */

export interface SupportSummaryInput {
  /** Backend package version, e.g. "1.1.3". */
  appVersion: string;
  /** Modular build the artifact was produced from, e.g. "mock" or "cpu". */
  buildProfile: string;
  /** AI mode the user asked for. */
  configuredMode: string;
  /** AI mode the worker actually applied. */
  appliedMode: string;
  aiEnabled: boolean;
  /** Acceleration preference enum ("auto" | "gpu" | "cpu"), never a device name. */
  accelMode: string;
  workerState: string;
  /** Seconds since the worker last reported in, when known. */
  workerAgeSeconds?: number | null;
  restartRequired?: boolean;
}

/** "unknown" rather than a fabricated number when the field is absent. */
export function formatWorkerAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "unknown";
  }
  const whole = Math.max(0, Math.round(seconds));
  if (whole < 60) return `${whole}s ago`;
  if (whole < 3600) return `${Math.round(whole / 60)}m ago`;
  return `${Math.round(whole / 3600)}h ago`;
}

/** Human-readable, copy-pasteable summary. Newline separated, no trailing newline. */
export function buildSupportSummary(input: SupportSummaryInput): string {
  const lines = [
    "Find support summary",
    `App version: ${input.appVersion}`,
    `Build profile: ${input.buildProfile}`,
    `AI: ${input.aiEnabled ? "enabled" : "disabled"}`,
    `AI mode: ${input.configuredMode} configured, ${input.appliedMode} applied`,
    `Acceleration: ${input.accelMode}`,
    `Worker: ${input.workerState}, last seen ${formatWorkerAge(
      input.workerAgeSeconds,
    )}`,
  ];

  if (input.restartRequired) {
    lines.push("Restart required: yes");
  }

  return lines.join("\n");
}
