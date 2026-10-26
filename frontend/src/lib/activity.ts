/**
 * Activity feed formatting (pure, no React).
 *
 * Turns a raw {category, action, payload} row from `/api/activity` into a
 * human-readable line and a chronological day-grouped list, kept pure so
 * both are unit-testable without rendering the page.
 */

import type { ActivityItem } from "@/lib/api";

export type ActivityTone = "positive" | "negative" | "neutral";

const POSITIVE_ACTIONS = new Set([
  "completed",
  "restored",
  "unlocked",
  "unarchived",
  "created",
]);

/** Success/failure/neutral, used to pick the badge color for a row. */
export function activityTone(item: ActivityItem): ActivityTone {
  if (item.action === "failed") return "negative";
  if (POSITIVE_ACTIONS.has(item.action)) return "positive";
  return "neutral";
}

function payloadString(item: ActivityItem, key: string): string | null {
  const value = item.payload?.[key];
  return typeof value === "string" ? value : null;
}

/** One human-readable line describing what happened, for the feed row. */
export function describeActivity(item: ActivityItem): string {
  const filename = payloadString(item, "filename");
  const reason = payloadString(item, "reason");
  const photo = item.media_id ? `photo #${item.media_id}` : "a photo";

  switch (`${item.category}.${item.action}`) {
    case "upload.completed":
      return `Uploaded ${filename ?? photo}`;
    case "upload.failed":
      return `Failed to process ${filename ?? photo}${
        reason ? ` — ${reason}` : ""
      }`;
    case "media.archived":
      return `Archived ${photo}`;
    case "media.unarchived":
      return `Unarchived ${photo}`;
    case "media.trashed":
      return `Moved ${photo} to trash`;
    case "media.restored":
      return `Restored ${photo}`;
    case "vault.created":
      return "Vault created";
    case "vault.unlocked":
      return "Vault unlocked";
    case "vault.locked":
      return "Vault locked";
    case "vault.restored":
      return `Restored ${photo} from the vault`;
    case "settings.updated": {
      const key = payloadString(item, "key");
      if (!key) return "Changed a setting";
      const from = item.payload?.from;
      const to = item.payload?.to;
      return `Changed ${key} from ${String(from)} to ${String(to)}`;
    }
    default:
      return `${item.category}.${item.action}`;
  }
}

export interface ActivityDayGroup {
  label: string;
  items: ActivityItem[];
}

function dayLabel(iso: string | null): string {
  if (!iso) return "Unknown date";
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (sameDay(date, today)) return "Today";
  if (sameDay(date, yesterday)) return "Yesterday";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

/** Group already-sorted (newest-first) items into day buckets, in order. */
export function groupActivityByDay(items: ActivityItem[]): ActivityDayGroup[] {
  const groups: ActivityDayGroup[] = [];
  for (const item of items) {
    const label = dayLabel(item.created_at);
    const current = groups.at(-1);
    if (current && current.label === label) {
      current.items.push(item);
    } else {
      groups.push({ label, items: [item] });
    }
  }
  return groups;
}
