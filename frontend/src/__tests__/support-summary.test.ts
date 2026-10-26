import { describe, expect, it } from "vitest";
import {
  buildSupportSummary,
  formatWorkerAge,
  type SupportSummaryInput,
} from "@/lib/support-summary";

const input: SupportSummaryInput = {
  appVersion: "1.1.3",
  buildProfile: "cpu",
  configuredMode: "full",
  appliedMode: "full",
  aiEnabled: true,
  accelMode: "auto",
  workerState: "healthy",
  workerAgeSeconds: 12,
};

describe("formatWorkerAge", () => {
  it("reports seconds, minutes, and hours", () => {
    expect(formatWorkerAge(5)).toBe("5s ago");
    expect(formatWorkerAge(150)).toBe("3m ago");
    expect(formatWorkerAge(7200)).toBe("2h ago");
  });

  it("says unknown rather than inventing a number", () => {
    expect(formatWorkerAge(null)).toBe("unknown");
    expect(formatWorkerAge(undefined)).toBe("unknown");
    expect(formatWorkerAge(Number.NaN)).toBe("unknown");
  });

  it("clamps a negative clock skew to zero", () => {
    expect(formatWorkerAge(-4)).toBe("0s ago");
  });
});

describe("buildSupportSummary", () => {
  it("includes the runtime facts a maintainer needs", () => {
    const summary = buildSupportSummary(input);

    expect(summary).toContain("App version: 1.1.3");
    expect(summary).toContain("Build profile: cpu");
    expect(summary).toContain("AI: enabled");
    expect(summary).toContain("AI mode: full configured, full applied");
    expect(summary).toContain("Acceleration: auto");
    expect(summary).toContain("Worker: healthy, last seen 12s ago");
  });

  it("marks AI off and flags a pending restart", () => {
    const summary = buildSupportSummary({
      ...input,
      aiEnabled: false,
      restartRequired: true,
    });

    expect(summary).toContain("AI: disabled");
    expect(summary).toContain("Restart required: yes");
  });

  it("omits the restart line when none is pending", () => {
    expect(buildSupportSummary(input)).not.toContain("Restart required");
  });

  // The privacy contract for #355: the summary is an allow-list, so anything
  // resembling a path, filename, credential, or identifier must not appear
  // even when a caller passes extra keys through.
  it("never emits fields outside the allow-list", () => {
    const summary = buildSupportSummary({
      ...input,
      ...({
        databaseUrl: "postgresql://find:secret@localhost:5432/find",
        mediaRoot: "/home/abhash/Pictures/private",
        filename: "passport-scan.jpg",
        sessionToken: "find_session_abcdef123456",
        username: "abhash",
        instanceId: "b4d1e0c2-9f3a-4e77-8c21-5a6f0d9e1b33",
      } as unknown as SupportSummaryInput),
    });

    for (const leak of [
      "postgresql://",
      "secret",
      "/home/abhash",
      "passport-scan.jpg",
      "find_session_abcdef123456",
      "abhash",
      "b4d1e0c2",
    ]) {
      expect(summary).not.toContain(leak);
    }
  });

  it("degrades to unknown instead of empty values", () => {
    const summary = buildSupportSummary({
      appVersion: "unknown",
      buildProfile: "unknown",
      configuredMode: "unknown",
      appliedMode: "unknown",
      aiEnabled: false,
      accelMode: "unknown",
      workerState: "unavailable",
      workerAgeSeconds: null,
    });

    expect(summary).toContain("App version: unknown");
    expect(summary).toContain("Worker: unavailable, last seen unknown");
  });
});
