import { expect, test } from "@playwright/test";

/**
 * Navigation accessibility E2E (#346).
 *
 * jsdom cannot prove either half of this issue: it has no CSS layout, so it
 * cannot show whether the desktop nav is clipped at a given width, and it has
 * no real focus order. Both live here instead, and like the other specs in this
 * directory they need no backend -- the shell and nav render even when every
 * API call fails.
 */

const THEMES = ["dark", "light"] as const;

const NAV_LABELS = [
  "Photos",
  "Search",
  "Map",
  "People",
  "Albums",
  "Favorites",
  "Duplicates",
  "Clusters",
  "Archive",
  "Vault",
  "Trash",
  "Activity",
  "Settings",
] as const;

const DRAWER = "[data-mobile-drawer]";

async function applyTheme(
  page: import("@playwright/test").Page,
  theme: string,
) {
  await page.evaluate((t) => {
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(t);
    document.documentElement.dataset.theme = t;
  }, theme);
}

test.describe("desktop navigation is reachable, not clipped", () => {
  // The issue called out the lg breakpoint specifically.
  for (const width of [1024, 1280, 1440]) {
    for (const theme of THEMES) {
      test(`every link is fully inside the viewport at ${width}px (${theme})`, async ({
        page,
      }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto("/timeline");
        await applyTheme(page, theme);

        const nav = page.getByRole("navigation", { name: "Main navigation" });
        await expect(nav).toBeVisible();

        for (const label of NAV_LABELS) {
          const link = nav.getByRole("link", { name: label, exact: true });
          await expect(link).toBeVisible();

          const box = await link.boundingBox();
          expect(box, `${label} has no layout box`).not.toBeNull();
          if (!box) continue;

          // Rendered with real size and not cut off on either edge.
          expect(box.width, `${label} collapsed`).toBeGreaterThan(0);
          expect(box.height, `${label} collapsed`).toBeGreaterThan(0);
          expect(
            box.x,
            `${label} clipped at the left edge`,
          ).toBeGreaterThanOrEqual(0);
          expect(
            box.x + box.width,
            `${label} clipped at the right edge`,
          ).toBeLessThanOrEqual(width + 0.5);
        }
      });
    }
  }
});

test.describe("mobile drawer behaves as an accessible modal", () => {
  for (const theme of THEMES) {
    test(`traps focus and restores the trigger (${theme})`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto("/timeline");
      await applyTheme(page, theme);

      const trigger = page.getByRole("button", {
        name: "Open navigation menu",
      });
      await expect(trigger).toBeVisible();
      await expect(trigger).toHaveAttribute("aria-expanded", "false");

      await trigger.click();

      const drawer = page.getByRole("dialog", { name: "Navigation menu" });
      await expect(drawer).toBeVisible();
      await expect(drawer).toHaveAttribute("aria-modal", "true");

      // Background is inert while the drawer owns the viewport. Being absent
      // from the accessibility tree entirely is the assertion that matters --
      // getByRole cannot see an aria-hidden landmark, which is the point.
      await expect(page.getByRole("banner")).toHaveCount(0);
      await expect(page.locator("header").first()).toHaveAttribute(
        "aria-hidden",
        "true",
      );
      await expect(
        page.evaluate(() => getComputedStyle(document.body).overflow),
      ).resolves.toBe("hidden");

      // Focus starts inside.
      await expect(
        page.evaluate(
          (sel) =>
            !!document.querySelector(sel)?.contains(document.activeElement),
          DRAWER,
        ),
      ).resolves.toBe(true);

      // A full lap of tabbing never escapes.
      for (let i = 0; i < NAV_LABELS.length + 6; i += 1) {
        await page.keyboard.press("Tab");
        const inside = await page.evaluate(
          (sel) =>
            !!document.querySelector(sel)?.contains(document.activeElement),
          DRAWER,
        );
        expect(inside, `focus escaped on tab ${i + 1}`).toBe(true);
      }

      // Shift+Tab wraps backwards without escaping either.
      for (let i = 0; i < 4; i += 1) {
        await page.keyboard.press("Shift+Tab");
        const inside = await page.evaluate(
          (sel) =>
            !!document.querySelector(sel)?.contains(document.activeElement),
          DRAWER,
        );
        expect(inside, `focus escaped on shift+tab ${i + 1}`).toBe(true);
      }

      await page.keyboard.press("Escape");

      await expect(drawer).toBeHidden();
      await expect(
        page.evaluate(() => document.body.style.overflow),
      ).resolves.toBe("");
      await expect(trigger).toBeFocused();
      // The shell is handed back to assistive tech once the drawer closes.
      await expect(page.getByRole("banner")).toHaveCount(1);
    });

    test(`drawer text stays readable in ${theme} mode`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto("/timeline");
      await applyTheme(page, theme);

      await page.getByRole("button", { name: "Open navigation menu" }).click();
      await expect(
        page.getByRole("dialog", { name: "Navigation menu" }),
      ).toBeVisible();

      // Every colour resolves through CSS custom properties, so a theme/palette
      // mismatch shows up as a label painted in its own effective background.
      // The active link supplies its own background, so each label has to be
      // compared against the nearest painted ancestor rather than the drawer.
      const samples = await page.evaluate((sel) => {
        const drawer = document.querySelector(sel) as HTMLElement;

        const paintedBackground = (node: HTMLElement): string => {
          let current: HTMLElement | null = node;
          while (current) {
            const bg = getComputedStyle(current).backgroundColor;
            if (
              bg &&
              bg !== "transparent" &&
              !bg.startsWith("rgba(0, 0, 0, 0")
            ) {
              return bg;
            }
            current = current.parentElement;
          }
          return "rgb(255, 255, 255)";
        };

        return Array.from(drawer.querySelectorAll("a")).map((link) => {
          const label = link.querySelector("span") as HTMLElement;
          return {
            text: label.textContent ?? "",
            fg: getComputedStyle(label).color,
            bg: paintedBackground(label),
          };
        });
      }, DRAWER);

      expect(samples.length).toBeGreaterThan(0);
      for (const { text, fg, bg } of samples) {
        expect(fg, `${text} is invisible against its own background`).not.toBe(
          bg,
        );
        expect(fg, `${text} has fully transparent text`).not.toBe(
          "rgba(0, 0, 0, 0)",
        );
      }
    });
  }
});
