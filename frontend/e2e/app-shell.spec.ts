import { expect, test } from "@playwright/test";

/**
 * App-shell smoke E2E (plan §10.2, browser layer).
 *
 * Asserts the real Next.js app renders its shell + new routes in a real
 * browser, without requiring a live backend: every assertion targets static
 * shell/nav chrome that renders even when API calls fail. Data-path journeys
 * against seeded data are the next layer (need a live stack) — the
 * server-observable journey is already covered by the API-level test
 * (backend/tests/test_e2e_journey.py).
 */

test.describe("app shell", () => {
  test("renders nav, brand, and footer on the timeline route", async ({
    page,
  }) => {
    await page.goto("/timeline");

    // Brand mark in the sticky nav.
    await expect(page.getByRole("link", { name: /FIND\./ })).toBeVisible();
    // Footer carries the AGPL license line (relicensed per §1).
    await expect(page.getByText(/AGPL-3\.0 License/)).toBeVisible();
  });

  test("exposes the new feature routes in the nav", async ({ page }) => {
    await page.goto("/");

    // The desktop nav lists the overhaul features.
    for (const label of [
      "Timeline",
      "Albums",
      "Archive",
      "Trash",
      "Settings",
    ]) {
      await expect(
        page.getByRole("link", { name: label, exact: true }).first(),
      ).toBeVisible();
    }
  });

  test("navigates to the settings route and shows the accel toggle", async ({
    page,
  }) => {
    await page.goto("/settings");

    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    // The hardware-acceleration section heading renders regardless of backend.
    await expect(
      page.getByRole("heading", { name: "Hardware acceleration" }),
    ).toBeVisible();
  });

  test("renders the timeline heading", async ({ page }) => {
    await page.goto("/timeline");
    await expect(page.getByRole("heading", { name: "Timeline" })).toBeVisible();
  });
});
