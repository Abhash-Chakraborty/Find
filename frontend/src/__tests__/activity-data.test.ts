/**
 * Unit tests for the pure activity feed formatting helpers.
 *
 * Run with: pnpm vitest run src/__tests__/activity-data.test.ts
 */

import { describe, expect, it } from "vitest";
import {
  activityTone,
  describeActivity,
  groupActivityByDay,
} from "@/lib/activity";
import type { ActivityItem } from "@/lib/api";

function item(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: 1,
    category: "media",
    action: "trashed",
    user_id: null,
    media_id: 42,
    payload: null,
    created_at: "2026-07-20T10:00:00+00:00",
    ...overrides,
  };
}

describe("activityTone", () => {
  it("marks failed as negative", () => {
    expect(activityTone(item({ action: "failed" }))).toBe("negative");
  });

  it("marks completed/restored/unlocked/unarchived/created as positive", () => {
    for (const action of [
      "completed",
      "restored",
      "unlocked",
      "unarchived",
      "created",
    ]) {
      expect(activityTone(item({ action }))).toBe("positive");
    }
  });

  it("marks everything else as neutral", () => {
    for (const action of ["trashed", "archived", "locked", "updated"]) {
      expect(activityTone(item({ action }))).toBe("neutral");
    }
  });
});

describe("describeActivity", () => {
  it("describes a completed upload with its filename", () => {
    const text = describeActivity(
      item({
        category: "upload",
        action: "completed",
        payload: { filename: "beach.jpg" },
      }),
    );
    expect(text).toBe("Uploaded beach.jpg");
  });

  it("includes the sanitized reason for a failed upload", () => {
    const text = describeActivity(
      item({
        category: "upload",
        action: "failed",
        payload: { filename: "beach.jpg", reason: "TimeoutError: ..." },
      }),
    );
    expect(text).toContain("beach.jpg");
    expect(text).toContain("TimeoutError");
  });

  it("falls back to the media id when no filename is in the payload", () => {
    const text = describeActivity(
      item({ category: "media", action: "trashed", media_id: 7 }),
    );
    expect(text).toBe("Moved photo #7 to trash");
  });

  it("describes a settings change with the key and values", () => {
    const text = describeActivity(
      item({
        category: "settings",
        action: "updated",
        media_id: null,
        payload: { key: "accel_mode", from: "auto", to: "gpu" },
      }),
    );
    expect(text).toBe("Changed accel_mode from auto to gpu");
  });

  it("describes vault events without needing a media id", () => {
    expect(
      describeActivity(
        item({ category: "vault", action: "unlocked", media_id: null }),
      ),
    ).toBe("Vault unlocked");
  });

  it("falls back to a raw category.action label for unknown combinations", () => {
    expect(describeActivity(item({ category: "widget", action: "spun" }))).toBe(
      "widget.spun",
    );
  });
});

describe("groupActivityByDay", () => {
  it("groups consecutive same-day items under one label", () => {
    const groups = groupActivityByDay([
      item({ id: 1, created_at: "2026-07-20T10:00:00+00:00" }),
      item({ id: 2, created_at: "2026-07-20T09:00:00+00:00" }),
      item({ id: 3, created_at: "2026-07-18T09:00:00+00:00" }),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups[0]?.items.map((entry) => entry.id)).toEqual([1, 2]);
    expect(groups[1]?.items.map((entry) => entry.id)).toEqual([3]);
  });

  it("labels a null created_at as Unknown date rather than throwing", () => {
    const groups = groupActivityByDay([item({ created_at: null })]);
    expect(groups[0]?.label).toBe("Unknown date");
  });
});
