import { expect, test } from "@playwright/test";

/**
 * PWA installability + offline shell E2E (#259).
 *
 * Like the other specs here, this needs no live backend: everything asserted is
 * static shell, manifest, and service-worker plumbing that renders even when
 * API calls fail.
 *
 * Note on the service worker itself: `pnpm start` serves over plain HTTP on
 * localhost, which browsers treat as a secure context, so registration does
 * happen here. What cannot be asserted in this environment is the *install
 * prompt*, which Chrome gates behind engagement heuristics -- so these cases
 * check the preconditions for installability rather than the prompt.
 */

test.describe("PWA manifest", () => {
  test("links a manifest describing a standalone Find app", async ({
    page,
    request,
  }) => {
    await page.goto("/timeline");

    const href = await page
      .locator('link[rel="manifest"]')
      .first()
      .getAttribute("href");
    expect(href).toBeTruthy();

    const response = await request.get(href as string);
    expect(response.ok()).toBe(true);

    const manifest = await response.json();
    expect(manifest.name).toContain("Find");
    expect(manifest.short_name).toBe("Find");
    expect(manifest.display).toBe("standalone");
    expect(manifest.start_url).toBe("/");

    // Chrome requires both a 192px and a 512px icon before it will offer
    // installation, so a missing size is a silent installability failure.
    const sizes = (manifest.icons ?? []).map(
      (icon: { sizes: string }) => icon.sizes,
    );
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
  });

  test("serves both declared icons", async ({ request }) => {
    for (const path of ["/icon-192.png", "/icon-512.png"]) {
      const response = await request.get(path);
      expect(response.ok(), `${path} should be served`).toBe(true);
      expect(response.headers()["content-type"]).toContain("image");
    }
  });

  test("declares a theme colour matching the manifest", async ({
    page,
    request,
  }) => {
    await page.goto("/timeline");

    const themeColor = await page
      .locator('meta[name="theme-color"]')
      .first()
      .getAttribute("content");
    const manifest = await (await request.get("/manifest.json")).json();

    // A mismatch here shows up as an installed app whose title bar disagrees
    // with its splash screen.
    expect(themeColor?.toLowerCase()).toBe(manifest.theme_color.toLowerCase());
  });
});

test.describe("offline shell", () => {
  test("serves a self-contained offline fallback page", async ({ page }) => {
    await page.goto("/offline.html");

    await expect(
      page.getByRole("heading", { name: /can.t reach your library/i }),
    ).toBeVisible();
    await expect(page.getByText(/staged on this device/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();

    // It must not depend on the app bundle -- if the network is down, no
    // Next.js chunk is going to load.
    await expect(page.locator('script[src*="/_next/"]')).toHaveCount(0);
    await expect(page.locator('link[rel="stylesheet"]')).toHaveCount(0);
  });

  test("registers a service worker that controls the page", async ({
    page,
  }) => {
    await page.goto("/timeline");

    const registered = await page.evaluate(async () => {
      if (!("serviceWorker" in navigator)) return false;
      const registration = await navigator.serviceWorker.ready;
      return Boolean(registration.active);
    });

    expect(registered).toBe(true);
  });

  test("shows the offline page when a navigation fails", async ({
    page,
    context,
  }) => {
    // Warm the service worker so the fallback is in its cache.
    await page.goto("/timeline");
    await page.evaluate(() => navigator.serviceWorker.ready);

    await context.setOffline(true);
    await page.goto("/gallery").catch(() => {
      // A navigation to an uncached route can reject outright; the assertion
      // below is what actually decides the outcome.
    });

    await expect(
      page.getByRole("heading", { name: /can.t reach your library/i }),
    ).toBeVisible();

    await context.setOffline(false);
  });
});
