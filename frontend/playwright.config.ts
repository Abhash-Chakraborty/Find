import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright browser E2E (plan §10.2). This is the in-browser complement to the
 * API-level journey (backend/tests/test_e2e_journey.py): it boots the real
 * Next.js app and asserts the app shell + new routes render in a real browser.
 *
 * The smoke specs deliberately do NOT require a live backend — they assert the
 * static shell/nav/route scaffolding that renders even when API calls fail, so
 * the suite is runnable in CI without standing up Postgres/MinIO/Redis. Full
 * data-path journeys (real share open, scrub-drag against seeded data) are the
 * next layer and need a live stack.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30 * 1000,
  expect: { timeout: 10 * 1000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "list" : "line",
  use: {
    baseURL: "http://localhost:3100",
    trace: "on-first-retry",
  },
  webServer: {
    // Start the production build on a dedicated port so it never collides with
    // a dev server on 3000. `pnpm build` must have run first (CI does).
    command: "pnpm start --port 3100",
    url: "http://localhost:3100",
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
